# Add this at the top of your app_kling.py file
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'  # Change this in production!
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///fashioncore.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Try-on configuration
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['RESULTS_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max upload size
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# Kling AI API configuration
app.config['KLING_API_URL'] = "https://api.klingai.com"
app.config['KLING_ACCESS_KEY'] = "7a3e661ac9f449e1a9416a9ad6aa7617"  # Change this to your actual access key
app.config['KLING_SECRET_KEY'] = "528c39f046024bc284c724457380ec1a"  # Change this to your actual secret key
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
    password_hash = db.Column(db.String(128))
    profile_image = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    credits = db.Column(db.Integer, default=3)  # Free try-on credits
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

# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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

@app.route('/')
def index():
    """Home page"""
    featured_products = Product.query.limit(6).all()
    return render_template('index.html', featured_products=featured_products)

# Kling AI Try-on routes
@app.route('/try-on-kling/<int:product_id>', methods=['GET'])
def try_on_kling_page(product_id):
    """Try-on page for a specific product using fashionCORE AI"""
    product = Product.query.get_or_404(product_id)
    # Check if user is logged in and has credits
    has_credits = False
    if current_user.is_authenticated:
        has_credits = current_user.credits > 0
    
    return render_template('tryon_kling.html', product=product, has_credits=has_credits)

@app.route('/try-on-kling', methods=['GET'])
def try_on_kling_generic():
    """Generic try-on page without a specific product using fashionCORE AI"""
    # Check if user is logged in and has credits
    has_credits = False
    if current_user.is_authenticated:
        has_credits = current_user.credits > 0
    
    return render_template('tryon_kling.html', product=None, has_credits=has_credits)

@app.route('/api/try-on-kling', methods=['POST'])
def try_on_kling_api():
    """API endpoint for virtual try-on using fashionCORE AI"""
    # Ensure user is authorized if logged in
    if current_user.is_authenticated and current_user.credits <= 0:
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
            
            return jsonify({
                "status": "success", 
                "result_url": f"/results/{result_filename}"
            })
        else:
            return jsonify(result), 500
            
    except Exception as e:
        return jsonify({
            "status": "error", 
            "message": str(e)
        }), 500
    
# Add these routes to your app_kling.py file

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

# Add these routes to your app_kling.py file

@app.route('/try-on', methods=['GET'])
def try_on_generic():
    """Generic try-on page without a specific product"""
    # Check if user is logged in and has credits
    has_credits = False
    if current_user.is_authenticated:
        has_credits = current_user.credits > 0
    
    return render_template('try_on.html', product=None, has_credits=has_credits)

@app.route('/try-on/<int:product_id>', methods=['GET'])
def try_on_page(product_id):
    """Try-on page for a specific product"""
    product = Product.query.get_or_404(product_id)
    # Check if user is logged in and has credits
    has_credits = False
    if current_user.is_authenticated:
        has_credits = current_user.credits > 0
    
    return render_template('try_on.html', product=product, has_credits=has_credits)

@app.route('/api/try-on', methods=['POST'])
def try_on_api():
    """API endpoint for virtual try-on"""
    # Ensure user is authorized if logged in
    if current_user.is_authenticated and current_user.credits <= 0:
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
            
            return jsonify({
                "status": "success", 
                "result_url": f"/results/{result_filename}"
            })
        else:
            return jsonify(result), 500
            
    except Exception as e:
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
    """Login page"""
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid email or password', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Register page"""
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already registered', 'warning')
        else:
            new_user = User(username=username, email=email)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful. Please log in.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    """Logout user"""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/results/<path:filename>')
def serve_result(filename):
    """Serve result images"""
    # Make sure we're using absolute path
    results_folder = os.path.abspath(app.config['RESULTS_FOLDER'])
    return send_from_directory(results_folder, filename)

@app.route('/debug-paths')
def debug_paths():
    """Debug route to check paths"""
    paths_info = {
        'RESULTS_FOLDER config': app.config['RESULTS_FOLDER'],
        'RESULTS_FOLDER absolute': os.path.abspath(app.config['RESULTS_FOLDER']),
        'RESULTS_FOLDER exists': os.path.exists(app.config['RESULTS_FOLDER']),
        'Results files': os.listdir(app.config['RESULTS_FOLDER']) if os.path.exists(app.config['RESULTS_FOLDER']) else [],
        'Current working directory': os.getcwd()
    }
    return jsonify(paths_info)

# Add these routes to the existing app
if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5001)