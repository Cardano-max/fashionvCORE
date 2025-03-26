"""
Admin routes and functionality for fashionCORE application

This module handles admin-specific routes, including:
- Admin authentication
- Dashboard display
- User management
- Try-on history viewing
- API key management
"""

from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, desc
from datetime import datetime, timedelta
import secrets
import uuid

# Import your database models
from models import db, User, TryOnHistory, Product, ApiKey, ApiUsage

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
    garment_count = db.session.query(func.count(func.distinct(TryOnHistory.garment_image_path))).scalar()
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
            'is_active': True,  # Assuming all users are active by default
            'try_on_count': try_on_count
        }
        users.append(user_data)
    
    # Get recent try-ons
    tryons = TryOnHistory.query.order_by(TryOnHistory.created_at.desc()).limit(10).all()
    
    # Get API usage data
    api_calls = ApiUsage.query.order_by(ApiUsage.timestamp.desc()).limit(10).all()
    
    # Get primary API key
    primary_api_key = "YOUR_API_KEY_HERE"  # Replace with actual API key retrieval
    
    return render_template(
        'admin_dashboard.html',
        user_count=user_count,
        tryon_count=tryon_count,
        garment_count=garment_count,
        api_count=api_count,
        users=users,
        tryons=tryons,
        api_calls=api_calls,
        primary_api_key=primary_api_key
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