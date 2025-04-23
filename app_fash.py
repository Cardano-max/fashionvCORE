from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session, send_from_directory, make_response
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
from authlib.integrations.flask_client import OAuth  # For Google OAuth
import logging
import json
import threading
import paypalrestsdk
import random
from flask_mail import Mail, Message

# Configure more detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Silence Werkzeug logs in production
logging.getLogger('werkzeug').setLevel(logging.ERROR)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your_secure_secret_key')

# Handle potential SQLAlchemy URI format differences
def get_database_url():
    """Get database URL and fix potential Railway formatting issues"""
    uri = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(app.root_path, 'tryontrend.db'))
    # Handle potential "postgres://" format from Railway (which SQLAlchemy doesn't accept)
    if uri.startswith('postgres://'):
        uri = uri.replace('postgres://', 'postgresql://', 1)
    return uri

# Replace the existing SQLALCHEMY_DATABASE_URI line with this:
app.config['SQLALCHEMY_DATABASE_URI'] = get_database_url()
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

# OAuth Configuration
app.config['GOOGLE_CLIENT_ID'] = os.environ.get('GOOGLE_CLIENT_ID')
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get('GOOGLE_CLIENT_SECRET')

# Log OAuth configuration (without exposing secret)
logger.info(f"Google Client ID configured: {'Yes' if app.config['GOOGLE_CLIENT_ID'] else 'No'}")
logger.info(f"Google Client Secret configured: {'Yes' if app.config['GOOGLE_CLIENT_SECRET'] else 'No'}")

# Stripe configuration
app.config['STRIPE_PUBLIC_KEY'] = os.environ.get('STRIPE_PUBLIC_KEY', 'pk_test_51O1x2xSI8ZUHBs6Zoi9nrDMB8F1TbN5RqQQkZjDGH9WlvKXaF7QXCpKPcnwRDAFJSNcSOTFp9K3iOkYzf6lSJsYl00CGfMdL1Y')
app.config['STRIPE_SECRET_KEY'] = os.environ.get('STRIPE_SECRET_KEY', 'sk_test_51O1x2xSI8ZUHBs6ZCMVbMbWGWpyYK7F3ODJ0PzZszDXEsLmI3bDYYmMmNkI8vXGWy2tNaPCGYF7sIrw0nTrkmwwY00xIubNmjq')
stripe.api_key = app.config['STRIPE_SECRET_KEY']

# Add these to your app configuration section
app.config['PAYPAL_CLIENT_ID'] = os.environ.get('PAYPAL_CLIENT_ID', '')
app.config['PAYPAL_CLIENT_SECRET'] = os.environ.get('PAYPAL_CLIENT_SECRET', '')
app.config['RAZORPAY_KEY_ID'] = os.environ.get('RAZORPAY_KEY_ID', '')
app.config['RAZORPAY_KEY_SECRET'] = os.environ.get('RAZORPAY_KEY_SECRET', '')

# Create upload and results folders if they don't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RESULTS_FOLDER'], exist_ok=True)
# Create static directory for payment method images if it doesn't exist
os.makedirs(os.path.join(app.root_path, 'static', 'images', 'payments'), exist_ok=True)
# Create static directory for videos if it doesn't exist
os.makedirs(os.path.join(app.root_path, 'static', 'videos'), exist_ok=True)

# Initialize database
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Initialize login manager
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Initialize OAuth
oauth = OAuth(app)

# Configure Google OAuth
google = oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    access_token_url='https://oauth2.googleapis.com/token',  # Updated from accounts.google.com
    access_token_params=None,
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    authorize_params={
        'access_type': 'offline',  # Get refresh token
        'prompt': 'consent'  # Force consent screen
    },
    api_base_url='https://www.googleapis.com/oauth2/v1/',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
    jwks_uri='https://www.googleapis.com/oauth2/v3/certs',
)

# Setup requests session with retry mechanism
def get_requests_session():
    """Configure requests session with retry logic"""
    session = requests.Session()
    retry_strategy = Retry(
        total=5,  # Increased from 3 to 5
        backoff_factor=2,  # Increased from 1 to 2
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
    password_hash = db.Column(db.String(128), nullable=True)  # Nullable for OAuth users
    profile_image = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    credits = db.Column(db.Integer, default=5)
    auth_provider = db.Column(db.String(20), default='local')  # 'local', 'google', etc.
    oauth_id = db.Column(db.String(100))  # OAuth provider ID
    orders = db.relationship('Order', backref='customer', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return self.password_hash and check_password_hash(self.password_hash, password)

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
    payment_method = db.Column(db.String(20))  # 'card', 'paypal', 'upi'
    payment_id = db.Column(db.String(100))  # Payment provider transaction ID
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    order_items = db.relationship('OrderItem', backref='order', lazy=True)
    shipping_address = db.Column(db.Text)
    billing_address = db.Column(db.Text)
    contact_email = db.Column(db.String(100))
    contact_phone = db.Column(db.String(20))

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

# Payment models
class PaymentTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    payment_method = db.Column(db.String(20), nullable=False)  # 'card', 'paypal', 'upi'
    provider = db.Column(db.String(20))  # 'stripe', 'paypal', 'gpay', 'phonepe'
    transaction_id = db.Column(db.String(100))
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default='INR')
    status = db.Column(db.String(20), default='pending')  # 'pending', 'completed', 'failed'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    response_data = db.Column(db.Text)  # JSON response from payment provider
    order = db.relationship('Order')
    user = db.relationship('User')

class OTP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), nullable=False)
    otp_code = db.Column(db.String(6), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False)

# Function to ensure database is initialized
def ensure_database():
    """Ensure database is initialized"""
    try:
        logger.info("Running database initialization check")
        # Create tables if they don't exist
        db.create_all()
        
        # Ensure admin user exists
        admin = User.query.filter_by(email='Shahkaushal26@gmail.com').first()
        if not admin:
            logger.info("Creating admin user during initialization")
            admin = User(
                username='admin',
                email='Shahkaushal26@gmail.com',
                is_admin=True,
                is_active=True,
                auth_provider='local'
            )
            admin.set_password('adminpassword')
            db.session.add(admin)
            db.session.commit()
            logger.info("Admin user created successfully")
        
        # Basic product initialization
        if Product.query.count() == 0:
            logger.info("Initializing products")
            init_db()
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}")

# Background task to clean up old images
def cleanup_old_images():
    """Background task to clean up ONLY unreferenced images that are NOT user uploads or garment images"""
    while True:
        try:
            logger.info("Running selective image cleanup task")
            
            # Clean up uploads folder - BUT NEVER DELETE PERSON OR GARMENT IMAGES
            uploads_folder = app.config['UPLOAD_FOLDER']
            for filename in os.listdir(uploads_folder):
                file_path = os.path.join(uploads_folder, filename)
                
                # Skip person and garment images completely - never delete these
                if filename.startswith('person_') or filename.startswith('garment_'):
                    continue
                    
                # For other files, check if older than 24 hours and not referenced
                file_modified = datetime.fromtimestamp(os.path.getmtime(file_path))
                cutoff_time = datetime.utcnow() - timedelta(hours=24)
                
                if file_modified < cutoff_time:
                    # Check if file is referenced in the database before deleting
                    person_refs = TryOnHistory.query.filter_by(person_image_path=filename).count()
                    garment_refs = TryOnHistory.query.filter_by(garment_image_path=filename).count()
                    
                    if person_refs == 0 and garment_refs == 0:
                        try:
                            os.remove(file_path)
                            logger.info(f"Deleted unreferenced file: {filename}")
                        except Exception as e:
                            logger.error(f"Error deleting file {filename}: {str(e)}")
            
            # Results folder - don't delete result images that are in database
            results_folder = app.config['RESULTS_FOLDER']
            for filename in os.listdir(results_folder):
                file_path = os.path.join(results_folder, filename)
                
                # Only check older files
                file_modified = datetime.fromtimestamp(os.path.getmtime(file_path))
                cutoff_time = datetime.utcnow() - timedelta(hours=24)
                
                if file_modified < cutoff_time:
                    # Check if file is referenced in the database before deleting
                    result_refs = TryOnHistory.query.filter_by(result_path=filename).count()
                    
                    if result_refs == 0:
                        try:
                            os.remove(file_path)
                            logger.info(f"Deleted unreferenced result: {filename}")
                        except Exception as e:
                            logger.error(f"Error deleting result {filename}: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error in cleanup task: {str(e)}")
            
        # Sleep for 1 hour before next cleanup
        time.sleep(3600)

# Replace before_first_request with before_request and add a check
db_initialized = False

@app.before_request
def check_database_initialized():
    """Check if database is initialized before handling requests"""
    global db_initialized
    if not db_initialized:
        ensure_database()
        db_initialized = True

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
    filename = f"{prefix}_{uuid.uuid4().hex}.{secure_filename(file.filename).rsplit('.', 1)[1].lower()}"
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
    if isinstance(token, bytes):
        token = token.decode('utf-8')  # For compatibility with different jwt versions
    return token

def image_to_base64(image_path):
    """Convert image to base64 encoded string"""
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    return encoded_string

# Global variable for API rate limiting
last_api_call_time = 0

def process_images(person_image_path, garment_image_path):
    """
    Process the images using the tryontrend AI API and return the result image.
    
    Args:
        person_image_path: Path to the person image file
        garment_image_path: Path to the garment image file
        
    Returns:
        Dict with status and result information
    """
    global last_api_call_time
    result_id = f"{uuid.uuid4().hex}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    result_filename = f"result_{result_id}.png"
    result_file_path = os.path.join(app.config['RESULTS_FOLDER'], result_filename)
    
    # Create a requests session with retry logic
    session = get_requests_session()
    
    # Add rate limiting
    current_time = time.time()
    if current_time - last_api_call_time < 2:  # 2 second minimum between requests
        time.sleep(2 - (current_time - last_api_call_time))
    last_api_call_time = time.time()
    
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
        
        logger.info("Creating tryontrend AI try-on task")
        try:
            response = session.post(
                f"{app.config['KLING_API_URL']}/v1/images/kolors-virtual-try-on",
                json=payload,
                headers=headers,
                timeout=app.config['KLING_REQUEST_TIMEOUT']
            )
        except requests.exceptions.ConnectTimeout:
            logger.error(f"Connection timeout while connecting to tryontrend AI API")
            return {"status": "error", "message": "Could not connect to try-on service. Please try again later."}
        except requests.exceptions.ConnectionError:
            logger.error(f"Connection error while connecting to tryontrend AI API")
            return {"status": "error", "message": "Connection to try-on service failed. Please check your internet connection."}
        except requests.exceptions.RequestException as e:
            logger.error(f"Request exception while connecting to tryontrend AI API: {str(e)}")
            return {"status": "error", "message": "An error occurred connecting to the try-on service."}
        
        try:
            response_data = response.json()
        except ValueError:
            logger.error(f"Invalid JSON response from tryontrend AI API")
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
                        "result_path": result_filename,  # Return just the filename, not full path
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

# Format address for database storage
def format_address(form_data):
    """Format address information from form data into a string for storage"""
    address_parts = [
        form_data.get('firstName', '') + ' ' + form_data.get('lastName', ''),
        form_data.get('address', ''),
        form_data.get('address2', ''),
        form_data.get('city', '') + ', ' + form_data.get('state', '') + ' ' + form_data.get('zip', ''),
        form_data.get('country', '')
    ]
    return '\n'.join(filter(None, address_parts))

# Database initialization function
def init_db():
    """Initialize database with default data"""
    logger.info("Starting database initialization")
    try:
        # Create admin user if not exists
        admin = User.query.filter_by(email='Shahkaushal26@gmail.com').first()
        if not admin:
            admin = User(
                username='admin',
                email='Shahkaushal26@gmail.com',
                is_admin=True,
                is_active=True,
                auth_provider='local'
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

        # Add payment method logos if they don't exist
        payment_methods = [
            {"name": "gpay", "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c7/Google_Pay_Logo_%282020%29.svg/512px-Google_Pay_Logo_%282020%29.svg.png"},
            {"name": "phonepe", "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5f/PhonePe_Logo.png/600px-PhonePe_Logo.png"},
            {"name": "paytm", "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/24/Paytm_Logo_%28standalone%29.svg/512px-Paytm_Logo_%28standalone%29.svg.png"},
            {"name": "upi", "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e1/UPI-Logo-vector.svg/1200px-UPI-Logo-vector.svg.png"}
        ]
        
        payment_dir = os.path.join(app.root_path, 'static', 'images', 'payments')
        
        for payment in payment_methods:
            payment_path = os.path.join(payment_dir, f"{payment['name']}.png")
            if not os.path.exists(payment_path):
                try:
                    # Download the logo
                    response = requests.get(payment['url'])
                    if response.status_code == 200:
                        with open(payment_path, 'wb') as f:
                            f.write(response.content)
                        logger.info(f"Downloaded payment logo: {payment['name']}")
                except Exception as e:
                    logger.error(f"Error downloading payment logo {payment['name']}: {str(e)}")

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


# Routes to serve uploaded files and results
@app.route('/results/<path:filename>')
def serve_result(filename):
    """Serve result images"""
    # Make sure we're using absolute path and secure the filename
    results_folder = os.path.abspath(app.config['RESULTS_FOLDER'])
    return send_from_directory(results_folder, secure_filename(filename))

@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    """Serve uploaded images"""
    # Make sure we're using absolute path and secure the filename
    uploads_folder = os.path.abspath(app.config['UPLOAD_FOLDER'])
    return send_from_directory(uploads_folder, secure_filename(filename))

# Kling AI Try-on routes
@app.route('/try-on-kling/<int:product_id>', methods=['GET'])
def try_on_kling_page(product_id):
    """Try-on page for a specific product using tryontrend AI"""
    product = Product.query.get_or_404(product_id)
    # Check if user is logged in and has credits
    has_credits = False
    if current_user.is_authenticated and current_user.is_active:
        has_credits = current_user.credits > 0
    
    return render_template('tryon_kling.html', product=product, has_credits=has_credits)

@app.route('/try-on-kling', methods=['GET'])
def try_on_kling_generic():
    """Generic try-on page without a specific product using tryontrend AI"""
    # Check if user is logged in and has credits
    has_credits = False
    if current_user.is_authenticated and current_user.is_active:
        has_credits = current_user.credits > 0
    
    return render_template('tryon_kling.html', product=None, has_credits=has_credits)

@app.route('/api/try-on-kling', methods=['POST'])
def try_on_kling_api():
    """API endpoint for virtual try-on using tryontrend AI"""
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
        # Save uploaded files with secure filenames
        person_filename = f"person_{uuid.uuid4().hex}.{secure_filename(person_image.filename).rsplit('.', 1)[1].lower()}"
        garment_filename = f"garment_{uuid.uuid4().hex}.{secure_filename(garment_image.filename).rsplit('.', 1)[1].lower()}"
        
        person_path = os.path.join(app.config['UPLOAD_FOLDER'], person_filename)
        garment_path = os.path.join(app.config['UPLOAD_FOLDER'], garment_filename)
        
        person_image.save(person_path)
        garment_image.save(garment_path)
        
        # Process the images
        result = process_images(person_path, garment_path)
        
        # Calculate response time for API tracking
        response_time = int((time.time() - start_time) * 1000)  # ms
        
        if result["status"] == "success":
            result_filename = result["result_path"]
            
            # If user is logged in, deduct a credit and save try-on history
            if current_user.is_authenticated:
                current_user.credits -= 1
                
                # Get product ID if provided
                product_id = request.form.get('product_id', None)
                if product_id:
                    try:
                        product_id = int(product_id)
                    except ValueError:
                        product_id = None
                
                # Save try-on history
                try_on_record = TryOnHistory(
                    user_id=current_user.id,
                    product_id=product_id,
                    result_path=result_filename,
                    person_image_path=person_filename,
                    garment_image_path=garment_filename,
                    kling_task_id=result.get("task_id", "")  # Store Kling AI task ID
                )
                
                db.session.add(try_on_record)
                db.session.commit()
                logger.info(f"Saved Kling try-on history record for user {current_user.id}")
            
            # Track API usage
            track_api_usage('/api/try-on-kling', 'POST', 200, response_time)
                
            return jsonify({
                "status": "success", 
                "result_url": url_for('serve_result', filename=result_filename)
            })
        else:
            # Track failed API usage
            track_api_usage('/api/try-on-kling', 'POST', 500, response_time)
            
            return jsonify(result), 500
            
    except Exception as e:
        # Track exception in API usage
        response_time = int((time.time() - start_time) * 1000)  # ms
        track_api_usage('/api/try-on-kling', 'POST', 500, response_time)
        logger.error(f"Kling try-on error: {str(e)}")
        
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
    
    # Check if user is authenticated
    if not current_user.is_authenticated:
        return jsonify({
            "status": "error",
            "message": "Please sign in to use the virtual try-on feature",
            "redirect": url_for('login')
        }), 401
    
    # Ensure user is authorized
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
        # Save uploaded files with secure filenames
        person_filename = f"person_{uuid.uuid4().hex}.{secure_filename(person_image.filename).rsplit('.', 1)[1].lower()}"
        garment_filename = f"garment_{uuid.uuid4().hex}.{secure_filename(garment_image.filename).rsplit('.', 1)[1].lower()}"
        
        person_path = os.path.join(app.config['UPLOAD_FOLDER'], person_filename)
        garment_path = os.path.join(app.config['UPLOAD_FOLDER'], garment_filename)
        
        person_image.save(person_path)
        garment_image.save(garment_path)
        
        # Process the images
        result = process_images(person_path, garment_path)
        
        # Calculate response time for API tracking
        response_time = int((time.time() - start_time) * 1000)  # ms
        
        if result["status"] == "success":
            result_filename = result["result_path"]
            
            # If user is logged in, deduct a credit and save try-on history
            if current_user.is_authenticated:
                current_user.credits -= 1
                
                # Get product ID if provided
                product_id = request.form.get('product_id', None)
                if product_id:
                    try:
                        product_id = int(product_id)
                    except ValueError:
                        product_id = None
                
                # Save try-on history
                try_on_record = TryOnHistory(
                    user_id=current_user.id,
                    product_id=product_id,
                    result_path=result_filename,
                    person_image_path=person_filename,
                    garment_image_path=garment_filename,
                    kling_task_id=result.get("task_id", "")  # Store Kling AI task ID
                )
                
                db.session.add(try_on_record)
                db.session.commit()
                logger.info(f"Saved try-on history record for user {current_user.id}")
            
            # Track API usage
            track_api_usage('/api/try-on', 'POST', 200, response_time)
                
            return jsonify({
                "status": "success", 
                "result_url": url_for('serve_result', filename=result_filename)
            })
        else:
            # Track failed API usage
            track_api_usage('/api/try-on', 'POST', 500, response_time)
            
            return jsonify(result), 500
            
    except Exception as e:
        # Track exception in API usage
        response_time = int((time.time() - start_time) * 1000)  # ms
        track_api_usage('/api/try-on', 'POST', 500, response_time)
        logger.error(f"Try-on error: {str(e)}")
        
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

# Authentication Routes

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
            
            # Set flag for showing promo video
            response = make_response(redirect(request.args.get('next') or url_for('index')))
            response.set_cookie('show_promo_video', 'true', max_age=60)  # Cookie valid for 60 seconds
            return response
        else:
            flash('Invalid email or password', 'danger')
            
    return render_template('auth/login.html')

@app.route('/login/google')
def login_google():
    """Initiate Google OAuth login"""
    logger.info("Starting Google login process")
    try:
        next_url = request.args.get('next')
        if next_url:
            session['next'] = next_url
        
        # Get the proper redirect URI based on the request
        if app.config.get('GOOGLE_REDIRECT_URI'):
            redirect_uri = app.config.get('GOOGLE_REDIRECT_URI')
        else:
            redirect_uri = url_for('google_callback', _external=True)
        
        logger.info(f"Using redirect URI: {redirect_uri}")
        
        # Store the redirect URI in the session to ensure consistency
        session['redirect_uri'] = redirect_uri
        
        return google.authorize_redirect(redirect_uri)
    except Exception as e:
        logger.error(f"Error initiating Google auth: {str(e)}")
        flash('Error initiating Google authentication. Please try again.', 'danger')
        return redirect(url_for('login'))

@app.route('/login/google/callback')
def google_callback():
    """Handle Google OAuth callback"""
    logger.info("Google callback started")
    try:
        # Get token
        token = google.authorize_access_token()
        logger.info(f"Received access token: {token.get('access_token', '')[:10]}...")
        
        # Get user info
        resp = google.get('userinfo')
        user_info = resp.json()
        logger.info(f"User info received: {user_info.get('email', 'no email')}")
        
        # Check for required fields
        if 'email' not in user_info:
            logger.error("Email not found in Google response")
            flash('Could not get email from Google. Please try again.', 'danger')
            return redirect(url_for('login'))
        
        # Check if user exists
        user = User.query.filter_by(email=user_info['email']).first()
        
        if user:
            # Update existing user if needed
            if user.auth_provider != 'google':
                user.auth_provider = 'google'
                user.oauth_id = user_info.get('id')
                db.session.commit()
                logger.info(f"Updated user {user.email} auth provider to Google")
        else:
            # Create new user
            username = user_info.get('name', user_info.get('email').split('@')[0])
            # Check if username exists and make it unique if needed
            if User.query.filter_by(username=username).first():
                username = f"{username}_{secrets.token_hex(4)}"
                
            new_user = User(
                username=username,
                email=user_info['email'],
                is_active=True,
                auth_provider='google',
                oauth_id=user_info.get('id'),
                profile_image=user_info.get('picture')
            )
            
            db.session.add(new_user)
            db.session.commit()
            logger.info(f"Created new user with Google auth: {new_user.email}")
            user = new_user
        
        # Update last login time
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        # Log in the user
        login_user(user)
        logger.info(f"Logged in user with Google: {user.email}")
        
        # Set flag for showing promo video
        response = make_response(redirect(session.pop('next', None) or url_for('index')))
        response.set_cookie('show_promo_video', 'true', max_age=60)  # Cookie valid for 60 seconds
        return response
        
    except Exception as e:
        logger.error(f"Google OAuth error: {str(e)}")
        flash('An error occurred during Google sign-in. Please try again.', 'danger')
        return redirect(url_for('login'))

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
    """Register a new user"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already registered. Please log in.', 'warning')
            return redirect(url_for('login'))
            
        # Generate and store OTP
        otp_code = generate_otp()
        expiry_time = datetime.utcnow() + timedelta(minutes=15)
        
        # Delete any existing OTPs for this email
        OTP.query.filter_by(email=email).delete()
        
        # Create new OTP record
        new_otp = OTP(
            email=email,
            otp_code=otp_code,
            expires_at=expiry_time
        )
        
        # Store password in session temporarily
        session['temp_password'] = password
        
        db.session.add(new_otp)
        db.session.commit()
        
        # Send verification email
        if send_verification_email(email, otp_code):
            # Explicitly redirect to OTP verification page
            return redirect(url_for('verify_otp', email=email))
        else:
            flash('Failed to send verification email. Please try again.', 'danger')
            
    return render_template('auth/register.html')

@app.route('/verify-otp/<email>', methods=['GET', 'POST'])
def verify_otp(email):
    """Verify OTP and create user account"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        entered_otp = request.form.get('otp')
        
        # Verify OTP
        otp_record = OTP.query.filter_by(
            email=email, 
            otp_code=entered_otp, 
            is_used=False
        ).first()
        
        if not otp_record:
            flash('Invalid OTP. Please try again.', 'danger')
            return render_template('auth/verify_otp.html', email=email)
            
        # Check if OTP is expired
        if datetime.utcnow() > otp_record.expires_at:
            flash('OTP has expired. Please request a new one.', 'danger')
            return redirect(url_for('register'))
            
        # Mark OTP as used
        otp_record.is_used = True
        
        # Create user account
        password = session.get('temp_password')
        if not password:
            flash('Session expired. Please register again.', 'danger')
            return redirect(url_for('register'))
            
        # Create username from email (before the @ symbol)
        username = email.split('@')[0]
        # If the username already exists, append numbers until unique
        base_username = username
        counter = 1
        while User.query.filter_by(username=username).first():
            username = f"{base_username}{counter}"
            counter += 1
            
        new_user = User(
            email=email,
            username=username,
            auth_provider='local'
        )
        new_user.set_password(password)
        
        # Clear session data
        session.pop('temp_password', None)
        
        db.session.add(new_user)
        db.session.commit()
        
        # Log the user in
        login_user(new_user)
        flash('Account created successfully!', 'success')
        
        return redirect(url_for('index'))
        
    # Make sure this GET request correctly renders the template
    return render_template('auth/verify_otp.html', email=email)

@app.route('/resend-otp/<email>')
def resend_otp(email):
    """Resend OTP for email verification"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    # Generate and store OTP
    otp_code = generate_otp()
    expiry_time = datetime.utcnow() + timedelta(minutes=15)
    
    # Delete any existing OTPs for this email
    OTP.query.filter_by(email=email).delete()
    
    # Create new OTP record
    new_otp = OTP(
        email=email,
        otp_code=otp_code,
        expires_at=expiry_time
    )
    
    db.session.add(new_otp)
    db.session.commit()
    
    # Send verification email
    if send_verification_email(email, otp_code):
        flash('New verification email sent. Please check your inbox.', 'info')
    else:
        flash('Failed to send verification email. Please try again.', 'danger')
    
    return redirect(url_for('verify_otp', email=email))

@app.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

# Checkout and Payment Routes
@app.route('/checkout')
@login_required
def checkout():
    """Checkout page"""
    return render_template('checkout.html', stripe_public_key=app.config['STRIPE_PUBLIC_KEY'])

@app.route('/process-payment', methods=['POST'])
@login_required
def process_payment():
    """Process credit card payment through Stripe"""
    try:
        # Get payment details
        payment_method_id = request.form.get('payment_method_id')
        amount = float(request.form.get('amount', 0))
        
        logger.info(f"Processing Stripe payment for user: {current_user.email}")
        
        # Create Stripe payment intent
        payment_intent = stripe.PaymentIntent.create(
            amount=int(amount * 100),  # Convert to cents
            currency='inr',
            payment_method=payment_method_id,
            confirm=True,
            return_url=url_for('checkout_complete', _external=True)
        )
        
        logger.info(f"Stripe PaymentIntent created: {payment_intent.id}")
        
        # Create order from cart
        shipping_address = format_address(request.form)
        order = Order(
            user_id=current_user.id,
            status='completed',
            total_amount=amount,
            payment_method='card',
            payment_id=payment_intent.id,
            shipping_address=shipping_address,
            contact_email=current_user.email,
            contact_phone=request.form.get('phone')
        )
        
        db.session.add(order)
        db.session.commit()
        
        # Record payment transaction
        transaction = PaymentTransaction(
            order_id=order.id,
            user_id=current_user.id,
            payment_method='card',
            provider='stripe',
            transaction_id=payment_intent.id,
            amount=amount,
            status='completed',
            response_data=str(payment_intent)
        )
        
        db.session.add(transaction)
        db.session.commit()
        
        # Add this function to extract cart items from JSON and create OrderItem records
        cart_items_json = request.form.get('cart_items')
        if cart_items_json:
            save_order_items(order.id, cart_items_json)
        
        logger.info(f"Payment successful: {payment_intent.id}")
        return jsonify({
            "success": True,
            "order_id": order.id,
            "transaction_id": payment_intent.id
        })
    
    except stripe.error.CardError as e:
        # Card declined
        error_msg = e.error.message
        logger.error(f"Card declined: {error_msg}")
        return jsonify({
            "success": False,
            "message": error_msg
        }), 400
        
    except stripe.error.StripeError as e:
        # Other Stripe errors
        logger.error(f"Stripe error: {str(e)}")
        return jsonify({
            "success": False,
            "message": "Payment processing error. Please try again."
        }), 500
        
    except Exception as e:
        # Generic error
        logger.error(f"Payment error: {str(e)}")
        return jsonify({
            "success": False,
            "message": "An unexpected error occurred. Please try again."
        }), 500

@app.route('/process-upi-payment', methods=['POST'])
@login_required
def process_upi_payment():
    """Process UPI payment with simulated integration"""
    try:
        # Get payment details
        upi_id = request.form.get('upi_id')
        upi_provider = request.form.get('upi_provider', 'other')
        amount = float(request.form.get('amount', 0))
        
        logger.info(f"Processing UPI payment for user: {current_user.email}")
        
        # In a real-world scenario, you would integrate with a UPI provider API
        # This could be RazorPay, Cashfree, PayU, etc. that offer UPI payment options
        
        # Example with RazorPay (you'd need to install the razorpay package)
        # import razorpay
        # client = razorpay.Client(auth=(app.config.get('RAZORPAY_KEY_ID'), app.config.get('RAZORPAY_KEY_SECRET')))
        
        # Create a unique transaction ID - in real implementation, this would come from the provider
        transaction_id = f"upi_{uuid.uuid4().hex}"
        
        # Example RazorPay code (commented out as it's just an example)
        # payment_data = {
        #     'amount': int(amount * 100),  # in paisa
        #     'currency': 'INR',
        #     'payment_capture': 1,
        #     'notes': {
        #         'upi_id': upi_id,
        #         'provider': upi_provider,
        #         'user_email': current_user.email
        #     }
        # }
        # payment = client.order.create(data=payment_data)
        # transaction_id = payment['id']
        
        # Create order from cart
        shipping_address = format_address(request.form)
        order = Order(
            user_id=current_user.id,
            status='completed',  # In a real implementation, this might start as 'pending'
            total_amount=amount,
            payment_method='upi',
            payment_id=transaction_id,
            shipping_address=shipping_address,
            contact_email=current_user.email,
            contact_phone=request.form.get('phone')
        )
        
        db.session.add(order)
        db.session.commit()
        
        # Record payment transaction
        transaction = PaymentTransaction(
            order_id=order.id,
            user_id=current_user.id,
            payment_method='upi',
            provider=upi_provider,
            transaction_id=transaction_id,
            amount=amount,
            status='completed'  # In a real implementation, might start as 'pending'
        )
        
        db.session.add(transaction)
        db.session.commit()
        
        # Add this function to extract cart items from JSON and create OrderItem records
        cart_items_json = request.form.get('cart_items')
        if cart_items_json:
            save_order_items(order.id, cart_items_json)
        
        # In a real integration, you might return data for a payment page or app redirection
        # For this example, we'll simulate success
        logger.info(f"UPI Payment successful: {transaction_id}")
        return jsonify({
            "success": True,
            "order_id": order.id,
            "transaction_id": transaction_id
        })
    
    except Exception as e:
        # Generic error
        logger.error(f"UPI Payment error: {str(e)}")
        return jsonify({
            "success": False,
            "message": "An error occurred processing your UPI payment. Please try again."
        }), 500

@app.route('/process-paypal-payment', methods=['POST'])
@login_required
def process_paypal_payment():
    """Process PayPal payment"""
    try:
        amount = float(request.form.get('amount', 0))
        
        # Check if PayPal SDK is available
        if not globals().get('PAYPAL_SDK_AVAILABLE', False):
            # Simulate PayPal payment
            transaction_id = f"paypal_{uuid.uuid4().hex}"
            
            # Create order
            shipping_address = format_address(request.form)
            order = Order(
                user_id=current_user.id,
                status='completed',
                total_amount=amount,
                payment_method='paypal',
                payment_id=transaction_id,
                shipping_address=shipping_address,
                contact_email=current_user.email,
                contact_phone=request.form.get('phone')
            )
            
            db.session.add(order)
            db.session.commit()
            
            # Record transaction
            transaction = PaymentTransaction(
                order_id=order.id,
                user_id=current_user.id,
                payment_method='paypal',
                provider='paypal',
                transaction_id=transaction_id,
                amount=amount,
                status='completed'
            )
            
            db.session.add(transaction)
            db.session.commit()
            
            # Add order items
            cart_items_json = request.form.get('cart_items')
            if cart_items_json:
                save_order_items(order.id, cart_items_json)
                
            return redirect(url_for('checkout_complete', order_id=order.id))
            
        # Original PayPal code continues here...
    except Exception as e:
        logger.error(f"PayPal Payment error: {str(e)}")
        flash('An error occurred processing your PayPal payment. Please try again.', 'danger')
        return redirect(url_for('checkout'))

@app.route('/paypal-return')
@login_required
def paypal_return():
    """Handle PayPal payment return"""
    payment_id = session.get('paypal_payment_id')
    order_id = session.get('order_id')
    payer_id = request.args.get('PayerID')
    
    if not (payment_id and payer_id and order_id):
        flash('Payment information missing. Please try again.', 'danger')
        return redirect(url_for('checkout'))
    
    try:
        import paypalrestsdk
        
        # Retrieve the payment object
        payment = paypalrestsdk.Payment.find(payment_id)
        
        # Execute the payment
        if payment.execute({"payer_id": payer_id}):
            # Update the order status
            order = Order.query.get(order_id)
            if order:
                order.status = 'completed'
                
                # Record payment transaction
                transaction = PaymentTransaction(
                    order_id=order.id,
                    user_id=current_user.id,
                    payment_method='paypal',
                    provider='paypal',
                    transaction_id=payment_id,
                    amount=order.total_amount,
                    status='completed',
                    response_data=str(payment)
                )
                
                db.session.add(transaction)
                db.session.commit()
                
                # Clear session data
                session.pop('paypal_payment_id', None)
                session.pop('order_id', None)
                
                # Redirect to checkout complete page
                return redirect(url_for('checkout_complete', order_id=order.id))
        else:
            logger.error(f"PayPal payment execution failed: {payment.error}")
            flash('Payment execution failed. Please try again.', 'danger')
            return redirect(url_for('checkout'))
            
    except Exception as e:
        logger.error(f"PayPal return error: {str(e)}")
        flash('An error occurred processing your payment. Please try again.', 'danger')
        return redirect(url_for('checkout'))

@app.route('/checkout-complete')
@login_required
def checkout_complete():
    """Checkout completion page"""
    order_id = request.args.get('order_id')
    order = None
    
    if order_id:
        order = Order.query.filter_by(id=order_id, user_id=current_user.id).first()
    
    return render_template('checkout_complete.html', order=order)

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

@app.route('/admin/users/<int:user_id>/add-credits', methods=['POST'])
@admin_required
def admin_add_credits(user_id):
    """Add credits to a user account (admin only)"""
    # Get user to add credits to
    user = User.query.get_or_404(user_id)
    
    try:
        # Get credits amount from request
        data = request.get_json()
        credits_to_add = int(data.get('credits', 0))
        
        if credits_to_add <= 0:
            return jsonify({
                'success': False,
                'message': 'Please provide a valid number of credits to add.'
            }), 400
        
        # Add credits to user
        user.credits += credits_to_add
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Added {credits_to_add} credits to {user.username}',
            'new_credit_balance': user.credits
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error adding credits: {str(e)}'
        }), 500

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

# Debug route for OAuth testing
@app.route('/debug-oauth')
def debug_oauth():
    """Debug OAuth configuration"""
    return jsonify({
        'GOOGLE_CLIENT_ID': app.config['GOOGLE_CLIENT_ID'][:10] + '...' if app.config['GOOGLE_CLIENT_ID'] else None,
        'GOOGLE_CLIENT_SECRET': app.config['GOOGLE_CLIENT_SECRET'][:5] + '...' if app.config['GOOGLE_CLIENT_SECRET'] else None,
        'google_callback_url': url_for('google_callback', _external=True),
        'server_url': request.url_root,
        'auth_providers': [user.auth_provider for user in User.query.limit(5).all()],
        'environment': {k: v for k, v in os.environ.items() if 'GOOGLE' in k},
    })

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

@click.command('set-admin-credentials')
def set_admin_credentials():
    """Set specific admin credentials"""
    try:
        # Check if admin with this email exists
        admin_email = "Shahkaushal26@gmail.com"
        admin_password = "admintryontrend@123"
        
        admin = User.query.filter_by(email=admin_email).first()
        
        if admin:
            # Update existing admin
            admin.set_password(admin_password)
            admin.is_admin = True
            db.session.commit()
            print(f"Updated admin credentials for {admin_email}")
        else:
            # Create new admin
            new_admin = User(
                username="admin",
                email=admin_email,
                is_admin=True
            )
            new_admin.set_password(admin_password)
            db.session.add(new_admin)
            db.session.commit()
            print(f"Created new admin user with email {admin_email}")
            
        print("Admin credentials set successfully!")
        
    except Exception as e:
        print(f"Error setting admin credentials: {str(e)}")

app.cli.add_command(init_db_command)
app.cli.add_command(create_admin_command)
app.cli.add_command(set_admin_credentials)

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', code=404, message="Page not found"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', code=500, message="Server error"), 500

@app.route('/profile')
@login_required
def profile():
    """User profile page"""
    return render_template('profile.html')

@app.route('/api/update-profile', methods=['POST'])
@login_required
def update_profile():
    """Update user profile information"""
    try:
        username = request.form.get('username')
        email = request.form.get('email')
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # Update username if changed
        if username and username != current_user.username:
            current_user.username = username

        # Update email if changed
        if email and email != current_user.email:
            current_user.email = email

        # Update password if provided
        if current_password and new_password and confirm_password:
            if not current_user.check_password(current_password):
                return jsonify({
                    'status': 'error',
                    'message': 'Current password is incorrect'
                }), 400
            
            if new_password != confirm_password:
                return jsonify({
                    'status': 'error',
                    'message': 'New passwords do not match'
                }), 400
            
            current_user.set_password(new_password)

        db.session.commit()
        return jsonify({
            'status': 'success',
            'message': 'Profile updated successfully'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/check-auth')
def check_auth():
    """Check if user is authenticated"""
    return jsonify({
        'authenticated': current_user.is_authenticated,
        'user': {
            'id': current_user.id if current_user.is_authenticated else None,
            'username': current_user.username if current_user.is_authenticated else None,
            'email': current_user.email if current_user.is_authenticated else None,
            'credits': current_user.credits if current_user.is_authenticated else 0
        }
    })

@app.route('/admin/export-users')
@admin_required
def admin_export_users():
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
        return redirect(url_for('admin_dashboard'))

# Start the cleanup thread when app starts
cleanup_thread = threading.Thread(target=cleanup_old_images, daemon=True)
cleanup_thread.start()

@app.route('/admin/analytics/data')
@admin_required
def admin_analytics_data():
    """Get real analytics data for the dashboard"""
    try:
        days = request.args.get('days', '30')
        try:
            days = int(days)
        except ValueError:
            days = 30
            
        # Calculate the date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Get real visits data (API usage as proxy)
        visits = ApiUsage.query.filter(ApiUsage.timestamp >= start_date).count()
        
        # Get real try-on data
        tryons = TryOnHistory.query.filter(TryOnHistory.created_at >= start_date).count()
        
        # Get real new users data
        new_users = User.query.filter(User.created_at >= start_date).count()
        
        # Get REAL daily visit data for chart
        daily_visits = []
        for day in range(days):
            day_date = start_date + timedelta(days=day)
            next_day = day_date + timedelta(days=1)
            
            # Count actual daily visits
            day_visits = ApiUsage.query.filter(
                ApiUsage.timestamp >= day_date,
                ApiUsage.timestamp < next_day
            ).count()
            
            daily_visits.append({
                'date': day_date.strftime('%m/%d'),
                'visits': day_visits
            })
            
        # Calculate previous period stats for change percentage
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
        
        # Calculate real change percentages
        visits_change = calculate_change_percent(visits, prev_visits)
        tryons_change = calculate_change_percent(tryons, prev_tryons)
        users_change = calculate_change_percent(new_users, prev_new_users)
        
        # Get REAL feature usage data
        feature_usage = {
            'tryons': tryons,
            'product_views': ApiUsage.query.filter(
                ApiUsage.timestamp >= start_date,
                ApiUsage.endpoint.like('%/product/%')
            ).count(),
            'account_creation': User.query.filter(
                User.created_at >= start_date
            ).count(),
            'purchases': Order.query.filter(
                Order.created_at >= start_date,
                Order.status == 'completed'
            ).count(),
            'shares': ApiUsage.query.filter(
                ApiUsage.timestamp >= start_date,
                ApiUsage.endpoint.like('%/share%')
            ).count()  # Count API calls related to shares
        }
        
        # Calculate real conversion rate if possible
        conversion_rate = 0
        if tryons > 0:
            purchases = Order.query.filter(
                Order.created_at >= start_date,
                Order.status == 'completed'
            ).count()
            conversion_rate = round((purchases / tryons) * 100, 1)
        
        # Calculate conversion rate change
        prev_conversion = 0
        if prev_tryons > 0:
            prev_purchases = Order.query.filter(
                Order.created_at >= prev_start_date,
                Order.created_at < start_date,
                Order.status == 'completed'
            ).count()
            prev_conversion = (prev_purchases / prev_tryons) * 100
        
        conversion_change = calculate_change_percent(conversion_rate, prev_conversion)
        
        # Return the actual data as JSON
        return jsonify({
            'visits': visits,
            'tryons': tryons,
            'new_users': new_users,
            'visits_change': visits_change,
            'tryons_change': tryons_change,
            'users_change': users_change,
            'conversion_rate': conversion_rate,
            'conversion_change': conversion_change,
            'daily_visits': daily_visits,
            'feature_usage': feature_usage
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def calculate_change_percent(current, previous):
    """Calculate percentage change between two periods"""
    if previous == 0:
        return 100 if current > 0 else 0
    return round(((current - previous) / previous) * 100, 1)

# Add this function to extract cart items from JSON and create OrderItem records
def save_order_items(order_id, cart_items_json):
    """Parse cart items JSON and create OrderItem records"""
    try:
        cart_items = json.loads(cart_items_json)
        for item in cart_items:
            # Create order item
            order_item = OrderItem(
                order_id=order_id,
                product_id=item.get('id'),
                quantity=item.get('quantity', 1),
                price=item.get('price', 0)
            )
            db.session.add(order_item)
        
        db.session.commit()
        logger.info(f"Saved {len(cart_items)} items for order {order_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving order items: {str(e)}")
        return False

def generate_otp():
    """Generate a 6-digit OTP"""
    return ''.join(random.choices('0123456789', k=6))

def send_verification_email(email, otp):
    """Send verification email with OTP"""
    subject = "Your TryOnTrend Verification Code"
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; margin: 0; padding: 0; background-color: #f4f4f4;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);">
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="color: #4361ee;">tryontrend</h1>
            </div>
            <h2 style="color: #333333;">Welcome to TryOnTrend!</h2>
            <p style="color: #555555; line-height: 1.6;">Thank you for signing up. Please use the verification code below to complete your registration:</p>
            <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; text-align: center; margin: 20px 0;">
                <h2 style="color: #4361ee; margin: 0; font-size: 32px; letter-spacing: 3px;">{otp}</h2>
            </div>
            <p style="color: #555555; line-height: 1.6;">This code will expire in 15 minutes.</p>
            <p style="color: #555555; line-height: 1.6;">If you didn't request this code, please ignore this email.</p>
            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #eeeeee; text-align: center; color: #999999; font-size: 12px;">
                <p>&copy; 2025 tryontrend. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    try:
        # Send actual email
        msg = Message(
            subject=subject,
            recipients=[email],
            html=body
        )
        mail.send(msg)
        logger.info(f"Verification email sent to {email}")
        return True
    except Exception as e:
        # For development, log the OTP so we can still test
        logger.error(f"Failed to send verification email: {str(e)}")
        logger.info(f"[DEV MODE] OTP for {email}: {otp}")
        flash(f"Email could not be sent. Please use this verification code: {otp}", "info")
        return True  # Return True so the flow continues even if email fails

# Add this near the top of your file, after initializing the Flask app
# Mail configuration
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@tryontrend.com')

mail = Mail(app)

# Only run this when the app is run directly
if __name__ == '__main__':
    # Ensure database is initialized when app starts
    with app.app_context():
        ensure_database()
    
    # Start the application
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))