"""
Admin routes and functionality for tryontrend application

This module handles admin-specific routes, including:
- Admin authentication
- Dashboard display
- User management
- Try-on history viewing
- API key management
"""
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, make_response
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, desc
from datetime import datetime, timedelta
import secrets
import uuid

# Import your database models
from models import db, User, TryOnHistory, Product, ApiKey, ApiUsage, Order
# Create blueprint
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Check if user is admin
def admin_required(f):
    """
    Decorator to check if the current user is an admin
    """
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Admin login
@admin_bp.route('/login', methods=['GET', 'POST'])
def admin_login():
    """
    Admin login route
    """
    # If user is already logged in and is admin, redirect to dashboard
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for('admin.dashboard'))
    
    # Handle login form submission
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Find user by email
        user = User.query.filter_by(email=email).first()
        
        # Check if user exists, is admin, and password is correct
        if user and user.is_admin and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Invalid admin credentials.', 'error')
    
    return render_template('admin_login.html')

# Admin dashboard
@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    """
    Admin dashboard route
    """
    # Get counts for dashboard stats
    user_count = User.query.count()
    tryon_count = TryOnHistory.query.count()
    garment_count = db.session.query(func.count(func.distinct(TryOnHistory.garment_image_path))).scalar() or 0
    api_count = ApiKey.query.filter_by(is_active=True).count()
    
    # Get users with try-on counts
    users_with_counts = db.session.query(
        User,
        func.count(TryOnHistory.id).label('try_on_count')
    ).outerjoin(
        TryOnHistory,
        User.id == TryOnHistory.user_id
    ).group_by(User.id).order_by(desc('try_on_count')).limit(10).all()
    
    # Format users for template
    users = []
    for user, try_on_count in users_with_counts:
        user_data = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'created_at': user.created_at,
            'is_active': user.is_active,
            'try_on_count': try_on_count
        }
        users.append(user_data)
    
    # Get recent try-ons
    tryons = TryOnHistory.query.order_by(TryOnHistory.created_at.desc()).limit(10).all()
    
    # Get API usage data
    api_calls = ApiUsage.query.order_by(ApiUsage.timestamp.desc()).limit(10).all()
    
    # Get primary API key
    primary_api_key = ApiKey.query.filter_by(is_active=True).first()
    if primary_api_key:
        primary_api_key = primary_api_key.key
    else:
        # Create a new API key if none exists
        primary_api_key = f"fcore_{secrets.token_hex(16)}"
        try:
            new_key = ApiKey(
                key=primary_api_key,
                name="Primary API Key",
                is_active=True,
                created_by=current_user.id
            )
            db.session.add(new_key)
            db.session.commit()
        except:
            # Handle case where we can't add the key (transaction issue)
            pass
    
    # Get analytics data for the last 30 days
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=30)
    
    # Total visits (API calls as proxy)
    total_visits = ApiUsage.query.filter(ApiUsage.timestamp >= start_date).count()
    
    # New users in the period
    new_users = User.query.filter(User.created_at >= start_date).count()
    
    # Calculate changes from previous period
    prev_start_date = start_date - timedelta(days=30)
    prev_visits = ApiUsage.query.filter(
        ApiUsage.timestamp >= prev_start_date,
        ApiUsage.timestamp < start_date
    ).count()
    
    prev_tryons = TryOnHistory.query.filter(
        TryOnHistory.created_at >= prev_start_date,
        TryOnHistory.created_at < start_date
    ).count()
    
    prev_new_users = User.query.filter(
        User.created_at >= prev_start_date,
        User.created_at < start_date
    ).count()
    
    # Calculate change percentages
    visits_change = calculate_change_percent(total_visits, prev_visits)
    tryons_change = calculate_change_percent(tryon_count, prev_tryons)
    users_change = calculate_change_percent(new_users, prev_new_users)
    
    # Conversion rate (try-on to purchase)
    conversion_rate = 3.5  # Demo fixed rate
    conversion_change = 0.2  # Demo change
    
    # Get user activity data
    user_activities = []
    
    # Get API usage as activity
    api_activities = ApiUsage.query.order_by(ApiUsage.timestamp.desc()).limit(50).all()
    for usage in api_activities:
        activity = {
            'timestamp': usage.timestamp,
            'user': usage.user,
            'action': 'API Call',
            'details': f"Endpoint: {usage.endpoint}, Status: {usage.status_code}"
        }
        user_activities.append(activity)
    
    # Get try-on data as activity
    tryon_activities = TryOnHistory.query.order_by(TryOnHistory.created_at.desc()).limit(50).all()
    for tryon in tryon_activities:
        activity = {
            'timestamp': tryon.created_at,
            'user': tryon.user,
            'action': 'Virtual Try-On',
            'details': f"Product: {tryon.product.name if tryon.product else 'Custom Garment'}"
        }
        user_activities.append(activity)
    
    # Sort by timestamp desc
    user_activities.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Limit to 50 most recent activities
    user_activities = user_activities[:50]
    
    return render_template(
        'admin_dashboard.html',
        user_count=user_count,
        tryon_count=tryon_count,
        garment_count=garment_count,
        api_count=api_count,
        users=users,
        tryons=tryons,
        api_calls=api_calls,
        primary_api_key=primary_api_key,
        # Analytics data
        total_visits=total_visits,
        new_users=new_users,
        visits_change=visits_change,
        tryons_change=tryons_change,
        users_change=users_change,
        conversion_rate=conversion_rate,
        conversion_change=conversion_change,
        user_activities=user_activities
    )

# Toggle user active status
@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@admin_required
def toggle_user_status(user_id):
    """
    Toggle user active status (block/unblock)
    """
    user = User.query.get_or_404(user_id)
    
    # Don't allow blocking of admin users
    if user.is_admin:
        return jsonify({'success': False, 'message': 'Cannot block admin users'})
    
    # Toggle is_active status
    user.is_active = not user.is_active
    db.session.commit()
    
    return jsonify({
        'success': True,
        'is_active': user.is_active,
        'message': f'User {"unblocked" if user.is_active else "blocked"} successfully'
    })

# Get user details
@admin_bp.route('/users/<int:user_id>')
@admin_required
def get_user_details(user_id):
    """
    Get detailed information about a user
    """
    user = User.query.get_or_404(user_id)
    
    # Get user's try-on history
    try_ons = TryOnHistory.query.filter_by(user_id=user_id).order_by(TryOnHistory.created_at.desc()).all()
    
    return render_template(
        'admin_user_details.html',
        user=user,
        try_ons=try_ons
    )

# View try-on details
@admin_bp.route('/tryons/<int:tryon_id>')
@admin_required
def get_tryon_details(tryon_id):
    """
    Get detailed information about a try-on
    """
    tryon = TryOnHistory.query.get_or_404(tryon_id)
    
    return render_template(
        'admin_tryon_details.html',
        tryon=tryon
    )

# Add new route to export user emails
@admin_bp.route('/export-users')
@admin_required
def export_users():
    """Export user emails and contact info as CSV"""
    try:
        # Get all users
        users = User.query.all()
        
        # Create CSV content
        csv_content = "id,username,email,created_at,last_login,is_active,credits\n"
        for user in users:
            # Format dates properly or use empty string if None
            created_at = user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else ""
            last_login = user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else ""
            
            # Add user data to CSV
            csv_content += f"{user.id},{user.username},{user.email},{created_at},{last_login},{user.is_active},{user.credits}\n"
        
        # Create response with CSV data
        response = make_response(csv_content)
        response.headers["Content-Disposition"] = "attachment; filename=users_export.csv"
        response.headers["Content-Type"] = "text/csv"
        
        return response
        
    except Exception as e:
        flash(f'Error exporting users: {str(e)}', 'error')
        return redirect(url_for('admin.dashboard'))

# Add analytics data API endpoint
@admin_bp.route('/analytics/data')
@admin_required
def get_analytics_data():
    """Get analytics data for the dashboard"""
    try:
        days = request.args.get('days', '30')
        try:
            days = int(days)
        except ValueError:
            days = 30
            
        # Calculate the date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Get user visits data (using API usage as a proxy for visits)
        visits = ApiUsage.query.filter(ApiUsage.timestamp >= start_date).count()
        
        # Get try-on data
        tryons = TryOnHistory.query.filter(TryOnHistory.created_at >= start_date).count()
        
        # Get new users data
        new_users = User.query.filter(User.created_at >= start_date).count()
        
        # Get daily visit data for chart
        daily_visits = []
        for day in range(days):
            day_date = start_date + timedelta(days=day)
            next_day = day_date + timedelta(days=1)
            day_visits = ApiUsage.query.filter(
                ApiUsage.timestamp >= day_date,
                ApiUsage.timestamp < next_day
            ).count()
            daily_visits.append({
                'date': day_date.strftime('%m/%d'),
                'visits': day_visits
            })
            
        # Calculate previous period for change percentage
        prev_start_date = start_date - timedelta(days=days)
        prev_visits = ApiUsage.query.filter(
            ApiUsage.timestamp >= prev_start_date,
            ApiUsage.timestamp < start_date
        ).count()
        
        prev_tryons = TryOnHistory.query.filter(
            TryOnHistory.created_at >= prev_start_date,
            TryOnHistory.created_at < start_date
        ).count()
        
        prev_new_users = User.query.filter(
            User.created_at >= prev_start_date,
            User.created_at < start_date
        ).count()
        
        # Calculate change percentages
        visits_change = calculate_change_percent(visits, prev_visits)
        tryons_change = calculate_change_percent(tryons, prev_tryons)
        users_change = calculate_change_percent(new_users, prev_new_users)
        
        # Get feature usage data
        feature_usage = {
            'tryons': tryons,
            'product_views': ApiUsage.query.filter(
                ApiUsage.timestamp >= start_date,
                ApiUsage.endpoint.like('%/product/%')
            ).count(),
            'account_creation': User.query.filter(User.created_at >= start_date).count(),
            'purchases': Order.query.filter(
                Order.created_at >= start_date,
                Order.status == 'completed'
            ).count(),
            'shares': 0  # Add your own metric for shares if you track them
        }
        
        # Calculate conversion rate (try-on to purchase)
        # You can customize this calculation based on your business metrics
        conversion_rate = 3.5  # Example fixed rate
        if tryons > 0:
            purchases = Order.query.filter(
                Order.created_at >= start_date,
                Order.status == 'completed'
            ).count()
            conversion_rate = (purchases / tryons) * 100
        
        conversion_change = 0.2  # Example change
        
        # Return the data as JSON
        return jsonify({
            'visits': visits,
            'tryons': tryons,
            'new_users': new_users,
            'visits_change': visits_change,
            'tryons_change': tryons_change,
            'users_change': users_change,
            'daily_visits': daily_visits,
            'feature_usage': feature_usage,
            'conversion_rate': conversion_rate,
            'conversion_change': conversion_change
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Helper function to calculate change percentage
def calculate_change_percent(current, previous):
    """Calculate percentage change between two periods"""
    if previous == 0:
        return 100 if current > 0 else 0
    return round(((current - previous) / previous) * 100, 1)

# User activity timeline data
@admin_bp.route('/analytics/activity')
@admin_required
def get_user_activity():
    """Get user activity timeline data"""
    try:
        # Get activity data (using API usage and tryons as activity sources)
        activities = []
        
        # Get API usage data
        api_usages = ApiUsage.query.order_by(ApiUsage.timestamp.desc()).limit(100).all()
        for usage in api_usages:
            activity = {
                'timestamp': usage.timestamp,
                'user': usage.user,
                'action': 'API Call',
                'details': f"Endpoint: {usage.endpoint}, Status: {usage.status_code}"
            }
            activities.append(activity)
        
        # Get try-on data
        tryons = TryOnHistory.query.order_by(TryOnHistory.created_at.desc()).limit(100).all()
        for tryon in tryons:
            activity = {
                'timestamp': tryon.created_at,
                'user': tryon.user,
                'action': 'Virtual Try-On',
                'details': f"Product: {tryon.product.name if tryon.product else 'Custom Garment'}"
            }
            activities.append(activity)
        
        # Sort by timestamp desc
        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Limit to 100 most recent activities
        activities = activities[:100]
        
        return render_template('admin_activity_timeline.html', activities=activities)
        
    except Exception as e:
        flash(f'Error loading activity data: {str(e)}', 'error')
        return redirect(url_for('admin.dashboard'))

# Generate new API key
@admin_bp.route('/api/generate-key', methods=['POST'])
@admin_required
def generate_api_key():
    """
    Generate a new API key
    """
    # Generate a secure random API key
    new_key = f"fcore_{secrets.token_hex(16)}"
    
    # Create new API key record
    api_key = ApiKey(
        key=new_key,
        name=request.form.get('name', 'API Key'),
        is_active=True,
        created_by=current_user.id
    )
    
    db.session.add(api_key)
    db.session.commit()
    
    flash('New API key generated successfully', 'success')
    return redirect(url_for('admin.dashboard') + '#api')

# Add these models to your models.py file

"""
class ApiKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    last_used = db.Column(db.DateTime)

class ApiUsage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    api_key_id = db.Column(db.Integer, db.ForeignKey('api_key.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    endpoint = db.Column(db.String(200), nullable=False)
    method = db.Column(db.String(10), nullable=False)
    status_code = db.Column(db.Integer, nullable=False)
    response_time = db.Column(db.Integer)  # in milliseconds
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(50))
"""

# Function to register the blueprint with your Flask app
def register_admin_blueprint(app):
    app.register_blueprint(admin_bp)