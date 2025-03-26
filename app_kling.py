from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
import uuid
import logging
import stripe
import time
import requests
import base64
import jwt  # Add JWT for Kling AI authentication
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv
import click
import secrets
from functools import wraps
from sqlalchemy import func, desc
from flask_migrate import Migrate

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your_secure_secret_key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///fashioncore.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Try-on configuration
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['RESULTS_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max upload size
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# Kling AI API configuration
app.config['KLING_API_URL'] = "https://api.klingai.com"
app.config['KLING_ACCESS_KEY'] = os.environ.get('KLING_ACCESS_KEY')
app.config['KLING_SECRET_KEY'] = os.environ.get('KLING_SECRET_KEY')
app.config['KLING_MODEL_NAME'] = "kolors-virtual-try-on-v1-5"  # Using the latest model version
app.config['KLING_REQUEST_TIMEOUT'] = 30  # Timeout in seconds for API requests
app.config['KLING_MAX_POLLING_ATTEMPTS'] = 30  # Maximum number of polling attempts
app.config['KLING_POLLING_INTERVAL'] = 5  # Seconds between polling attempts

# Stripe configuration
app.config['STRIPE_PUBLIC_KEY'] = 'your_stripe_public_key'
app.config['STRIPE_SECRET_KEY'] = 'your_stripe_secret_key'
stripe.api_key = app.config['STRIPE_SECRET_KEY'] 

# Create upload and results folders if they don't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RESULTS_FOLDER'], exist_ok=True)

# Initialize database
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Initialize login manager
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Setup requests session with retry mechanism
def get_requests_session():
    """Configure requests session with retry logic"""
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    profile_image = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)  # Add this field for user status
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)  # Add this field to track last login
    credits = db.Column(db.Integer, default=5)  # Free credits for new users
    orders = db.relationship('Order', backref='customer', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    image_path = db.Column(db.String(200))
    category = db.Column(db.String(50))
    brand = db.Column(db.String(50))
    stock = db.Column(db.Integer, default=100)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')
    total_amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    order_items = db.relationship('OrderItem', backref='order', lazy=True)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    price = db.Column(db.Float, nullable=False)
    product = db.relationship('Product')

class TryOnHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=True)
    result_path = db.Column(db.String(200))
    person_image_path = db.Column(db.String(200))
    garment_image_path = db.Column(db.String(200))
    kling_task_id = db.Column(db.String(200))  # Add Kling AI task ID for reference
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='try_on_history')
    product = db.relationship('Product')

# API-related models for admin dashboard
class ApiKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    last_used = db.Column(db.DateTime)
    user = db.relationship('User')

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
    api_key = db.relationship('ApiKey')
    user = db.relationship('User')

# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Admin decorator
def admin_required(f):
    """
    Decorator to check if the current user is an admin
    """
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Utility Functions
def allowed_file(filename):
    """Check if a file has an allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def save_uploaded_file(file, prefix):
    """Save an uploaded file with a unique name and return the path"""
    filename = f"{prefix}_{uuid.uuid4().hex}.{file.filename.rsplit('.', 1)[1].lower()}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    return filepath

def generate_kling_auth_token():
    """Generate JWT token for fashionCCORE AI API authentication"""
    headers = {
        "alg": "HS256",
        "typ": "JWT"
    }
    
    payload = {
        "iss": app.config['KLING_ACCESS_KEY'],
        "exp": int(time.time()) + 1800,  # Valid for 30 minutes
        "nbf": int(time.time()) - 5      # Valid from 5 seconds ago
    }
    
    token = jwt.encode(payload, app.config['KLING_SECRET_KEY'], headers=headers)
    return token

def image_to_base64(image_path):
    """Convert image to base64 encoded string"""
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    return encoded_string

def process_images(person_image_path, garment_image_path):
    """
    Process the images using the fashionCORE AI API and return the result image.
    
    Args:
        person_image_path: Path to the person image file
        garment_image_path: Path to the garment image file
        
    Returns:
        Dict with status and result information
    """
    result_id = f"{uuid.uuid4().hex}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    result_file_path = os.path.join(app.config['RESULTS_FOLDER'], f"result_{result_id}.png")
    
    # Create a requests session with retry logic
    session = get_requests_session()
    
    try:
        # Generate authentication token
        auth_token = generate_kling_auth_token()
        
        # Convert images to base64
        person_base64 = image_to_base64(person_image_path)
        garment_base64 = image_to_base64(garment_image_path)
        
        # Prepare request payload
        payload = {
            "model_name": app.config['KLING_MODEL_NAME'],
            "human_image": person_base64,
            "cloth_image": garment_base64
        }
        
        # Make API request to create try-on task
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {auth_token}"
        }
        
        logger.info("Creating fashionCORE AI try-on task")
        try:
            response = session.post(
                f"{app.config['KLING_API_URL']}/v1/images/kolors-virtual-try-on",
                json=payload,
                headers=headers,
                timeout=app.config['KLING_REQUEST_TIMEOUT']
            )
        except requests.exceptions.ConnectTimeout:
            logger.error(f"Connection timeout while connecting to fashionCORE AI API")
            return {"status": "error", "message": "Could not connect to try-on service. Please try again later."}
        except requests.exceptions.ConnectionError:
            logger.error(f"Connection error while connecting to fashionCORE AI API")
            return {"status": "error", "message": "Connection to try-on service failed. Please check your internet connection."}
        except requests.exceptions.RequestException as e:
            logger.error(f"Request exception while connecting to fashionCORE AI API: {str(e)}")
            return {"status": "error", "message": "An error occurred connecting to the try-on service."}
        
        try:
            response_data = response.json()
        except ValueError:
            logger.error(f"Invalid JSON response from fashionCORE AI API")
            return {"status": "error", "message": "Received invalid response from try-on service."}
        
        if response.status_code != 200 or response_data.get('code', -1) != 0:
            error_message = response_data.get('message', 'Unknown error')
            logger.error(f"Kling AI API error: {error_message}")
            return {"status": "error", "message": f"API Error: {error_message}"}
        
        # Get task ID from response
        task_id = response_data['data']['task_id']
        logger.info(f"Kling AI task created with ID: {task_id}")
        
        # Poll for task completion
        max_attempts = app.config['KLING_MAX_POLLING_ATTEMPTS']
        poll_interval = app.config['KLING_POLLING_INTERVAL']
        
        for attempt in range(max_attempts):
            logger.info(f"Polling task status (attempt {attempt+1}/{max_attempts})")
            
            # Regenerate auth token to ensure it's still valid
            auth_token = generate_kling_auth_token()
            headers["Authorization"] = f"Bearer {auth_token}"
            
            # Check task status
            try:
                status_response = session.get(
                    f"{app.config['KLING_API_URL']}/v1/images/kolors-virtual-try-on/{task_id}",
                    headers=headers,
                    timeout=app.config['KLING_REQUEST_TIMEOUT']
                )
            except requests.exceptions.RequestException as e:
                logger.warning(f"Error checking task status: {str(e)}")
                # Continue polling despite the error
                time.sleep(poll_interval)
                continue
            
            try:
                status_data = status_response.json()
            except ValueError:
                logger.warning("Invalid JSON in status response")
                time.sleep(poll_interval)
                continue
            
            if status_response.status_code != 200 or status_data.get('code', -1) != 0:
                error_message = status_data.get('message', 'Unknown error')
                logger.error(f"Kling AI API error while checking status: {error_message}")
                time.sleep(poll_interval)
                continue
            
            task_status = status_data['data']['task_status']
            logger.info(f"Task status: {task_status}")
            
            if task_status == 'failed':
                error_message = status_data['data'].get('task_status_msg', 'Task processing failed')
                logger.error(f"Task processing failed: {error_message}")
                return {"status": "error", "message": error_message}
            
            if task_status == 'succeed':
                # Get result image URL
                result_images = status_data['data']['task_result']['images']
                if not result_images:
                    logger.error("No result images found in completed task")
                    return {"status": "error", "message": "No result images found"}
                
                result_url = result_images[0]['url']
                logger.info(f"Result image URL: {result_url}")
                
                # Download result image
                try:
                    img_response = session.get(result_url, timeout=app.config['KLING_REQUEST_TIMEOUT'])
                    if img_response.status_code != 200:
                        logger.error(f"Failed to download result image: HTTP {img_response.status_code}")
                        return {"status": "error", "message": "Failed to download result image"}
                    
                    # Save result image
                    with open(result_file_path, 'wb') as f:
                        f.write(img_response.content)
                    
                    logger.info(f"Result image saved to {result_file_path}")
                    return {
                        "status": "success", 
                        "result_path": result_file_path,
                        "task_id": task_id
                    }
                except requests.exceptions.RequestException as e:
                    logger.error(f"Error downloading result image: {str(e)}")
                    return {"status": "error", "message": f"Error downloading result image: {str(e)}"}
            
            # Wait before next polling attempt
            time.sleep(poll_interval)
        
        # If we reach here, polling timed out
        logger.error("Timeout waiting for task completion")
        return {"status": "error", "message": "Timeout waiting for task completion. Please try again later."}
        
    except Exception as e:
        logger.error(f"Error during image processing: {str(e)}")
        return {"status": "error", "message": f"An unexpected error occurred: {str(e)}"}

# Track API usage
def track_api_usage(endpoint, method='GET', status_code=200, response_time=0, api_key_id=None):
    """Track API usage for admin dashboard"""
    try:
        api_usage = ApiUsage(
            api_key_id=api_key_id,
            user_id=current_user.id if current_user.is_authenticated else None,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            response_time=response_time,
            ip_address=request.remote_addr
        )
        db.session.add(api_usage)
        db.session.commit()
    except Exception as e:
        logger.error(f"Error tracking API usage: {str(e)}")
        # Don't let API tracking errors affect the main functionality
        db.session.rollback()

# Database initialization function
def init_db():
    """Initialize database with default data"""
    logger.info("Starting database initialization")
    try:
        # Create admin user if not exists
        admin = User.query.filter_by(email='admin@fashioncore.com').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@fashioncore.com',
                is_admin=True,
                is_active=True
            )
            admin.set_password('adminpassword')
            db.session.add(admin)
            logger.info("Admin user created")

        # Add new products for the Featured Collection
        products = [
            {"name": "Kanchipuram Silk Saree", "description": "Elegant traditional silk saree perfect for weddings and celebrations.", "price": 129.99, "image_path": "images/products/kanchipuram_silk_saree.jpg", "category": "Sarees", "brand": "Ameezara Creation"},
            {"name": "Banarasi Silk Saree", "description": "Exquisite Banarasi silk saree known for its intricate weaving.", "price": 149.99, "image_path": "images/products/Banarasi Silk Saree.jpg", "category": "Sarees", "brand": "Ameezara Creation"},
            {"name": "Bridal Lehenga Choli", "description": "Bridal lehenga choli set perfect for weddings.", "price": 199.99, "image_path": "images/products/Bridal Lehenga Choli.jpg", "category": "Lehengas", "brand": "Ameezara Creation"},
            {"name": "Designer Anarkali Suit", "description": "Designer Anarkali suit with intricate embroidery and a luxurious look.", "price": 159.99, "image_path": "images/products/Designer Anarkali Suit.jpg", "category": "Suits", "brand": "Ameezara Creation"},
            {"name": "Designer Palazzo Kurti Set", "description": "Stylish palazzo and kurti set designed for modern women.", "price": 89.99, "image_path": "images/products/Designer Palazzo Kurti Set.jpg", "category": "Kurti Sets", "brand": "Ameezara Creation"},
            {"name": "Embellished Sharara Set", "description": "Beautifully embellished Sharara set with detailed work.", "price": 179.99, "image_path": "images/products/Embellished Sharara Set .jpg", "category": "Sharara Sets", "brand": "Ameezara Creation"}
        ]

        for product_data in products:
            existing_product = Product.query.filter_by(name=product_data["name"]).first()
            if not existing_product:
                product = Product(
                    name=product_data["name"],
                    description=product_data["description"],
                    price=product_data["price"],
                    image_path=product_data["image_path"],
                    category=product_data["category"],
                    brand=product_data["brand"]
                )
                db.session.add(product)
                logger.info(f"Product added: {product_data['name']}")

        db.session.commit()
        logger.info("Database initialization completed successfully")

    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        db.session.rollback()
        raise

# Debug route to check database products
@app.route('/debug-db')
def debug_db():
    """Debug route to check database contents"""
    products = Product.query.all()
    return jsonify({
        'product_count': len(products),
        'products': [
            {
                'id': p.id,
                'name': p.name,
                'image_path': p.image_path,
                'exists': os.path.exists(os.path.join('static', p.image_path))
            }
            for p in products
        ]
    })

# Main Routes

# Make sure to initialize database before the first index page load
@app.route('/')
def index():
    try:
        # Check if database needs initialization
        if Product.query.count() == 0:
            init_db()
            logger.info("Database initialized on first index page load")
    except:
        # If there's an error, the tables might not exist yet
        with app.app_context():
            db.create_all()
            init_db()
            logger.info("Database created and initialized on first index page load")
    
    # Query the products for the featured section
    featured_products = Product.query.filter(Product.name.in_([
        'Kanchipuram Silk Saree',
        'Banarasi Silk Saree',
        'Bridal Lehenga Choli',
        'Designer Anarkali Suit',
        'Designer Palazzo Kurti Set',
        'Embellished Sharara Set'
    ])).all()

    return render_template('index.html', featured_products=featured_products)


# Kling AI Try-on routes
@app.route('/try-on-kling/<int:product_id>', methods=['GET'])
def try_on_kling_page(product_id):
    """Try-on page for a specific product using fashionCORE AI"""
    product = Product.query.get_or_404(product_id)
    # Check if user is logged in and has credits
    has_credits = False
    if current_user.is_authenticated and current_user.is_active:
        has_credits = current_user.credits > 0
    
    return render_template('tryon_kling.html', product=product, has_credits=has_credits)

@app.route('/try-on-kling', methods=['GET'])
def try_on_kling_generic():
    """Generic try-on page without a specific product using fashionCORE AI"""
    # Check if user is logged in and has credits
    has_credits = False
    if current_user.is_authenticated and current_user.is_active:
        has_credits = current_user.credits > 0
    
    return render_template('tryon_kling.html', product=None, has_credits=has_credits)

@app.route('/api/try-on-kling', methods=['POST'])
def try_on_kling_api():
    """API endpoint for virtual try-on using fashionCORE AI"""
    start_time = time.time()
    
    # Ensure user is authorized if logged in
    if current_user.is_authenticated:
        if not current_user.is_active:
            return jsonify({
                "status": "error",
                "message": "Your account is currently inactive. Please contact support."
            }), 403
        if current_user.credits <= 0:
            return jsonify({
                "status": "error",
                "message": "You have no try-on credits left. Please purchase credits to continue."
            }), 403
    
    # Check if files exist in the request
    if 'person_image' not in request.files or 'garment_image' not in request.files:
        return jsonify({
            "status": "error", 
            "message": "Both person and garment images are required"
        }), 400
    
    person_image = request.files['person_image']
    garment_image = request.files['garment_image']
    
    # Check if the files are allowed
    if not allowed_file(person_image.filename) or not allowed_file(garment_image.filename):
        return jsonify({
            "status": "error", 
            "message": "Only image files (PNG, JPG, JPEG, GIF) are allowed"
        }), 400
    
    try:
        # Save uploaded files
        person_path = save_uploaded_file(person_image, 'person')
        garment_path = save_uploaded_file(garment_image, 'garment')
        
        # Process the images
        result = process_images(person_path, garment_path)
        
        # Calculate response time for API tracking
        response_time = int((time.time() - start_time) * 1000)  # ms
        
        if result["status"] == "success":
            result_path = result["result_path"]
            result_filename = os.path.basename(result_path)
            
            # If user is logged in, deduct a credit and save try-on history
            if current_user.is_authenticated:
                current_user.credits -= 1
                
                # Get product ID if provided
                product_id = request.form.get('product_id', None)
                
                # Save try-on history
                try_on_record = TryOnHistory(
                    user_id=current_user.id,
                    product_id=product_id,
                    result_path=result_filename,
                    person_image_path=os.path.basename(person_path),
                    garment_image_path=os.path.basename(garment_path),
                    kling_task_id=result.get("task_id", "")  # Store Kling AI task ID
                )
                
                db.session.add(try_on_record)
                db.session.commit()
            
            # Track API usage
            track_api_usage('/api/try-on-kling', 'POST', 200, response_time)
                
            return jsonify({
                "status": "success", 
                "result_url": f"/results/{result_filename}"
            })
        else:
            # Track failed API usage
            track_api_usage('/api/try-on-kling', 'POST', 500, response_time)
            
            return jsonify(result), 500
            
    except Exception as e:
        # Track exception in API usage
        response_time = int((time.time() - start_time) * 1000)  # ms
        track_api_usage('/api/try-on-kling', 'POST', 500, response_time)
        
        return jsonify({
            "status": "error", 
            "message": str(e)
        }), 500

@app.route('/products')
def products():
    """All products page"""
    category = request.args.get('category')
    search = request.args.get('search')
    
    query = Product.query
    
    if category:
        query = query.filter_by(category=category)
    
    if search:
        query = query.filter(Product.name.contains(search) | Product.description.contains(search))
    
    products = query.all()
    categories = db.session.query(Product.category).distinct().all()
    
    return render_template('products.html', products=products, categories=categories)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    """Product detail page"""
    product = Product.query.get_or_404(product_id)
    
    # Get related products
    related_products = Product.query.filter(
        Product.category == product.category, 
        Product.id != product.id
    ).limit(4).all()
    
    return render_template('product_detail.html', product=product, related_products=related_products)

@app.route('/business-try-on')
def business_try_on():
    """Business try-on page"""
    return render_template('business_try_on.html')

@app.route('/privacy-policy')
def privacy_policy():
    """Privacy policy page"""
    return render_template('privacy_policy.html')

@app.route('/terms-of-service')
def terms_of_service():
    """Terms of service page"""
    return render_template('terms_of_service.html')

@app.route('/api/docs')
def api_docs():
    """API documentation page"""
    return render_template('api_docs.html')

@app.route('/cart')
def cart():
    """Shopping cart page"""
    if not current_user.is_authenticated:
        flash('Please log in to view your cart', 'warning')
        return redirect(url_for('login'))
        
    return render_template('cart.html')

@app.route('/try-on', methods=['GET'])
def try_on_generic():
    """Generic try-on page without a specific product"""
    # Check if user is logged in and has credits
    has_credits = False
    if current_user.is_authenticated and current_user.is_active:
        has_credits = current_user.credits > 0
    
    return render_template('try_on.html', product=None, has_credits=has_credits)

@app.route('/try-on/<int:product_id>', methods=['GET'])
def try_on_page(product_id):
    """Try-on page for a specific product"""
    product = Product.query.get_or_404(product_id)
    # Check if user is logged in and has credits
    has_credits = False
    if current_user.is_authenticated and current_user.is_active:
        has_credits = current_user.credits > 0
    
    return render_template('try_on.html', product=product, has_credits=has_credits)

@app.route('/api/try-on', methods=['POST'])
def try_on_api():
    """API endpoint for virtual try-on"""
    start_time = time.time()
    
    # Ensure user is authorized if logged in
    if current_user.is_authenticated:
        if not current_user.is_active:
            return jsonify({
                "status": "error",
                "message": "Your account is currently inactive. Please contact support."
            }), 403
        if current_user.credits <= 0:
            return jsonify({
                "status": "error",
                "message": "You have no try-on credits left. Please purchase credits to continue."
            }), 403
    
    # Check if files exist in the request
    if 'person_image' not in request.files or 'garment_image' not in request.files:
        return jsonify({
            "status": "error", 
            "message": "Both person and garment images are required"
        }), 400
    
    person_image = request.files['person_image']
    garment_image = request.files['garment_image']
    
    # Check if the files are allowed
    if not allowed_file(person_image.filename) or not allowed_file(garment_image.filename):
        return jsonify({
            "status": "error", 
            "message": "Only image files (PNG, JPG, JPEG, GIF) are allowed"
        }), 400
    
    try:
        # Save uploaded files
        person_path = save_uploaded_file(person_image, 'person')
        garment_path = save_uploaded_file(garment_image, 'garment')
        
        # Process the images
        result = process_images(person_path, garment_path)
        
        # Calculate response time for API tracking
        response_time = int((time.time() - start_time) * 1000)  # ms
        
        if result["status"] == "success":
            result_path = result["result_path"]
            result_filename = os.path.basename(result_path)
            
            # If user is logged in, deduct a credit and save try-on history
            if current_user.is_authenticated:
                current_user.credits -= 1
                
                # Get product ID if provided
                product_id = request.form.get('product_id', None)
                
                # Save try-on history
                try_on_record = TryOnHistory(
                    user_id=current_user.id,
                    product_id=product_id,
                    result_path=result_filename,
                    person_image_path=os.path.basename(person_path),
                    garment_image_path=os.path.basename(garment_path),
                    kling_task_id=result.get("task_id", "")  # Store Kling AI task ID
                )
                
                db.session.add(try_on_record)
                db.session.commit()
            
            # Track API usage
            track_api_usage('/api/try-on', 'POST', 200, response_time)
                
            return jsonify({
                "status": "success", 
                "result_url": f"/results/{result_filename}"
            })
        else:
            # Track failed API usage
            track_api_usage('/api/try-on', 'POST', 500, response_time)
            
            return jsonify(result), 500
            
    except Exception as e:
        # Track exception in API usage
        response_time = int((time.time() - start_time) * 1000)  # ms
        track_api_usage('/api/try-on', 'POST', 500, response_time)
        
        return jsonify({
            "status": "error", 
            "message": str(e)
        }), 500
    
@app.route('/pricing')
def pricing():
    """Pricing page"""
    return render_template('pricing.html')

@app.route('/about')
def about():
    """About page"""
    return render_template('about.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login page"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = 'remember' in request.form
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            # Check if user is active
            if not user.is_active:
                flash('Your account has been deactivated. Please contact support.', 'danger')
                return render_template('auth/login.html')
                
            # Update last login time
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Invalid email or password', 'danger')
            
    return render_template('auth/login.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin_dashboard'))
        else:
            flash('You do not have admin privileges', 'danger')
            return redirect(url_for('index'))
            
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password) and user.is_admin:
            # Update last login time
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            login_user(user)
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid admin credentials', 'danger')
            
    return render_template('admin_login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration page"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validation
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return render_template('auth/register.html')
            
        # Check if user already exists
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return render_template('auth/register.html')
            
        if User.query.filter_by(username=username).first():
            flash('Username already taken', 'danger')
            return render_template('auth/register.html')
            
        # Create new user
        new_user = User(username=username, email=email)
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Account created successfully! You can now log in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('auth/register.html')

@app.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

@app.route('/results/<path:filename>')
def serve_result(filename):
    """Serve result images"""
    # Make sure we're using absolute path
    results_folder = os.path.abspath(app.config['RESULTS_FOLDER'])
    return send_from_directory(results_folder, filename)

# Admin Dashboard Routes
@app.route('/admin')
@admin_required
def admin_dashboard():
    """Admin dashboard page"""
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
    ).group_by(User.id).all()
    
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
            logger.warning("Could not create primary API key - will be created on next access")
    
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

@app.route('/admin/users/<int:user_id>')
@admin_required
def admin_user_details(user_id):
    """Admin user details page"""
    user = User.query.get_or_404(user_id)
    
    # Get user's try-on history
    try_ons = TryOnHistory.query.filter_by(user_id=user_id).order_by(TryOnHistory.created_at.desc()).all()
    
    # Get unique garments count
    unique_garments = db.session.query(func.count(func.distinct(TryOnHistory.garment_image_path))).\
        filter(TryOnHistory.user_id == user_id).scalar()
    
    # Calculate days since last activity
    last_activity = None
    last_tryon = TryOnHistory.query.filter_by(user_id=user_id).order_by(TryOnHistory.created_at.desc()).first()
    
    if last_tryon:
        last_activity = last_tryon.created_at
    elif user.last_login:
        last_activity = user.last_login
    else:
        last_activity = user.created_at
        
    last_activity_days = (datetime.utcnow() - last_activity).days
    
    return render_template(
        'admin_user_details.html',
        user=user,
        try_ons=try_ons,
        unique_garments=unique_garments,
        last_activity_days=last_activity_days
    )

@app.route('/admin/users/<int:user_id>/toggle', methods=['POST'])
@admin_required
def admin_toggle_user(user_id):
    """Toggle user active status"""
    user = User.query.get_or_404(user_id)
    
    # Don't allow blocking admin users
    if user.is_admin and user.is_active:
        return jsonify({
            'success': False, 
            'message': 'Cannot block admin users'
        })
    
    # Toggle active status
    user.is_active = not user.is_active
    db.session.commit()
    
    return jsonify({
        'success': True,
        'is_active': user.is_active,
        'message': f"User has been {'activated' if user.is_active else 'blocked'} successfully"
    })

@app.route('/admin/tryons/<int:tryon_id>')
@admin_required
def admin_tryon_details(tryon_id):
    """Admin try-on details page"""
    tryon = TryOnHistory.query.get_or_404(tryon_id)
    
    # Get user's try-on count
    user_tryon_count = TryOnHistory.query.filter_by(user_id=tryon.user_id).count()
    
    # Estimate processing time (random for demonstration)
    processing_time = 15  # seconds
    
    return render_template(
        'admin_tryon_details.html',
        tryon=tryon,
        user_tryon_count=user_tryon_count,
        processing_time=processing_time,
        timedelta=timedelta  # Pass timedelta to the template
    )

@app.route('/admin/api/generate', methods=['POST'])
@admin_required
def admin_generate_api_key():
    """Generate a new API key"""
    key_name = request.form.get('key_name', 'API Key')
    
    # Generate a new API key
    new_key = f"fcore_{secrets.token_hex(16)}"
    
    # Save the key to the database
    api_key = ApiKey(
        key=new_key,
        name=key_name,
        is_active=True,
        created_by=current_user.id
    )
    
    db.session.add(api_key)
    db.session.commit()
    
    flash('New API key generated successfully', 'success')
    return redirect(url_for('admin_dashboard') + '#api')

@app.route('/admin/api/<int:key_id>/toggle', methods=['POST'])
@admin_required
def admin_toggle_api_key(key_id):
    """Toggle API key active status"""
    api_key = ApiKey.query.get_or_404(key_id)
    
    # Toggle active status
    api_key.is_active = not api_key.is_active
    db.session.commit()
    
    return jsonify({
        'success': True,
        'is_active': api_key.is_active,
        'message': f"API key has been {'activated' if api_key.is_active else 'deactivated'} successfully"
    })

@app.route('/debug-paths')
def debug_paths():
    """Debug route to check paths"""
    paths_info = {
        'RESULTS_FOLDER config': app.config['RESULTS_FOLDER'],
        'RESULTS_FOLDER absolute': os.path.abspath(app.config['RESULTS_FOLDER']),
        'RESULTS_FOLDER exists': os.path.exists(app.config['RESULTS_FOLDER']),
        'Results files': os.listdir(app.config['RESULTS_FOLDER']) if os.path.exists(app.config['RESULTS_FOLDER']) else [],
        'Current working directory': os.getcwd(),
        'Static folder': os.path.join(app.root_path, 'static'),
        'Product images': os.path.exists(os.path.join(app.root_path, 'static', 'images', 'products'))
    }
    return jsonify(paths_info)

# Flask CLI Commands
@click.command('init-db')
@click.pass_context
def init_db_command(ctx):
    """Clear the existing data and create new tables."""
    with app.app_context():
        db.create_all()
        init_db()
    click.echo('Initialized the database.')

@click.command('create-admin')
@click.argument('email')
@click.argument('username')
@click.argument('password')
def create_admin_command(email, username, password):
    """Create an admin user."""
    with app.app_context():
        # Check if user exists
        user = User.query.filter_by(email=email).first()
        if user:
            # Update existing user
            user.username = username
            user.set_password(password)
            user.is_admin = True
            user.is_active = True
            click.echo(f"User {email} updated and promoted to admin.")
        else:
            # Create new admin user
            admin = User(
                email=email,
                username=username,
                is_admin=True,
                is_active=True
            )
            admin.set_password(password)
            db.session.add(admin)
            click.echo(f"Admin user {email} created successfully.")
        
        db.session.commit()

app.cli.add_command(init_db_command)
app.cli.add_command(create_admin_command)

# Only run this when the app is run directly
if __name__ == '__main__':
    # Check if the database exists and initialize it if needed
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fashioncore.db')
    if not os.path.exists(db_path):
        with app.app_context():
            db.create_all()
            init_db()
    
    # Start the application
    app.run(debug=True, host='127.0.0.1', port=int(os.environ.get('PORT', 8080)))