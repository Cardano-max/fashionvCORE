from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
import uuid
import logging
import time
import requests
import jwt
import base64
from PIL import Image
import io

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

# Kling AI configuration
app.config['KLING_API_URL'] = 'https://api.klingai.com'
app.config['KLING_ACCESS_KEY'] = '7a3e661ac9f449e1a9416a9ad6aa7617'  # Replace with your actual key
app.config['KLING_SECRET_KEY'] = '528c39f046024bc284c724457380ec1a'  # Replace with your actual key

# Create upload and results folders if they don't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RESULTS_FOLDER'], exist_ok=True)

# Initialize database
db = SQLAlchemy(app)

# Initialize login manager
login_manager = LoginManager(app)
login_manager.login_view = 'login'

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
    return filepath, filename

def generate_jwt_token():
    """Generate JWT token for Kling AI API authentication"""
    headers = {
        "alg": "HS256",
        "typ": "JWT"
    }
    payload = {
        "iss": app.config['KLING_ACCESS_KEY'],
        "exp": int(time.time()) + 1800,  # 30 minutes expiry
        "nbf": int(time.time()) - 5  # Valid from 5 seconds ago
    }
    token = jwt.encode(payload, app.config['KLING_SECRET_KEY'], headers=headers)
    return token

def get_kling_headers():
    """Get headers for Kling AI API requests"""
    token = generate_jwt_token()
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }

def process_images(person_image_path, garment_image_path):
    """Process images with Kling AI virtual try-on service"""
    try:
        logger.info(f"Processing images: {person_image_path} and {garment_image_path}")
        
        # Read images as base64
        with open(person_image_path, 'rb') as f:
            person_image_data = f.read()
        
        with open(garment_image_path, 'rb') as f:
            garment_image_data = f.read()
        
        person_base64 = base64.b64encode(person_image_data).decode('utf-8')
        garment_base64 = base64.b64encode(garment_image_data).decode('utf-8')
        
        # Prepare payload for Kling AI
        payload = {
            "model_name": "kolors-virtual-try-on-v1-5",  # Using the improved V1.5 model
            "human_image": person_base64,
            "cloth_image": garment_base64,
            "seed": int(time.time()) % 1000000  # Random seed based on current time
        }
        
        # Make request to Kling AI
        response = requests.post(
            f"{app.config['KLING_API_URL']}/v1/images/kolors-virtual-try-on",
            headers=get_kling_headers(),
            json=payload
        )
        
        if response.status_code == 429:
            logger.error(f"API rate limit exceeded: {response.text}")
            return None, "Sorry, our service is currently at capacity. Please try again in a few minutes."
            
        if response.status_code != 200:
            logger.error(f"API error: {response.text}")
            return None, f"Error: API returned status code {response.status_code}"
        
        response_data = response.json()
        
        # Get task ID from response
        task_id = response_data.get('data', {}).get('task_id')
        
        if not task_id:
            logger.error("No task ID returned from Kling AI")
            return None, "No task ID returned from Kling AI"
        
        # Wait for task to complete
        max_attempts = 30
        for attempt in range(max_attempts):
            logger.info(f"Checking task status, attempt {attempt+1}/{max_attempts}")
            
            status_response = requests.get(
                f"{app.config['KLING_API_URL']}/v1/images/kolors-virtual-try-on/{task_id}",
                headers=get_kling_headers()
            )
            
            if status_response.status_code != 200:
                logger.error(f"Error checking task status: {status_response.text}")
                return None, f"Error checking task status: {status_response.status_code}"
            
            status_data = status_response.json()
            task_status = status_data.get('data', {}).get('task_status')
            
            if task_status == "succeed":
                task_result = status_data.get('data', {}).get('task_result', {})
                images = task_result.get('images', [])
                
                if images and len(images) > 0:
                    image_url = images[0].get('url')
                    if image_url:
                        # Download the result image
                        img_response = requests.get(image_url)
                        if img_response.status_code == 200:
                            result_filename = f"result_{uuid.uuid4().hex}.jpg"
                            result_path = os.path.join(app.config['RESULTS_FOLDER'], result_filename)
                            
                            with open(result_path, 'wb') as f:
                                f.write(img_response.content)
                            
                            return result_filename, "Success"
                
                return None, "No result image found"
            elif task_status == "failed":
                task_status_msg = status_data.get('data', {}).get('task_status_msg', 'Unknown error')
                logger.error(f"Task failed: {task_status_msg}")
                return None, f"Task failed: {task_status_msg}"
            
            # Wait before checking again
            time.sleep(2)
        
        return None, "Timeout waiting for task to complete"
        
    except Exception as e:
        logger.error(f"Error processing images: {str(e)}")
        return None, f"Error processing images: {str(e)}"

def process_business_images(model_path, garment_path, background_type, background_value):
    """Process the images for business try-on using Kling AI"""
    try:
        # For now, we'll use the same base processing as the regular try-on function
        result_filename, message = process_images(model_path, garment_path)
        
        # If the processing was successful, we'll apply the selected background
        if result_filename:
            result_path = os.path.join(app.config['RESULTS_FOLDER'], result_filename)
            
            try:
                # Apply the background to the result image
                if background_type == 'color':
                    # For solid colors, we'll need to manually set the background
                    try:
                        # Open the result image
                        img = Image.open(result_path).convert("RGBA")
                        
                        # Create a new image with the selected background color
                        # Convert hex color to RGB
                        bg_color = background_value.lstrip('#')
                        bg_color = tuple(int(bg_color[i:i+2], 16) for i in (0, 2, 4))
                        
                        # Create a new image with the background color
                        bg = Image.new('RGBA', img.size, bg_color + (255,))
                        
                        # Paste the result image onto the background
                        bg.paste(img, (0, 0), img)
                        
                        # Save the new image
                        bg.convert("RGB").save(result_path)
                        logger.info(f"Applied solid color background: {background_value}")
                    except Exception as e:
                        logger.error(f"Error applying solid color background: {str(e)}")
                elif background_type == 'image' and background_value:
                    try:
                        # Get the path to the background image
                        bg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                            'static', 'images', 'business', 'backgrounds', background_value)
                        
                        if os.path.exists(bg_path):
                            # Open the result image and background
                            result_img = Image.open(result_path).convert("RGBA")
                            bg_img = Image.open(bg_path).convert("RGBA")
                            
                            # Resize background to match result image if needed
                            bg_img = bg_img.resize(result_img.size, Image.LANCZOS)
                            
                            # Create a composite
                            composite = Image.alpha_composite(bg_img, result_img)
                            
                            # Save the new image
                            composite.convert("RGB").save(result_path)
                            logger.info(f"Applied image background: {background_value}")
                        else:
                            logger.warning(f"Background image not found: {bg_path}")
                    except Exception as e:
                        logger.error(f"Error applying image background: {str(e)}")
                
                return result_filename, "Success"
            except Exception as e:
                logger.error(f"Error applying background: {str(e)}")
                # If there was an error applying the background, still return the original result
                return result_filename, "Success"
        else:
            # If the processing failed, return the error
            return None, message
    except Exception as e:
        logger.error(f"Error processing business images: {str(e)}")
        return None, f"Error processing business images: {str(e)}"

# Routes
@app.route('/')
def index():
    """Home page"""
    featured_products = Product.query.limit(6).all()
    return render_template('index.html', featured_products=featured_products)

@app.route('/about')
def about():
    """About page"""
    return render_template('about.html')

@app.route('/pricing')
def pricing():
    """Pricing page"""
    return render_template('pricing.html')

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user, remember=True)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Invalid email or password', 'danger')
    
    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Registration page"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return render_template('auth/register.html')
        
        if User.query.filter_by(username=username).first():
            flash('Username already taken', 'danger')
            return render_template('auth/register.html')
        
        user = User(username=username, email=email)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('auth/register.html')

@app.route('/logout')
@login_required
def logout():
    """Logout user"""
    logout_user()
    return redirect(url_for('index'))

# Product routes
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

@app.route('/products/<int:product_id>')
def product_detail(product_id):
    """Product detail page"""
    product = Product.query.get_or_404(product_id)
    related_products = Product.query.filter_by(category=product.category).filter(Product.id != product.id).limit(4).all()
    return render_template('product_detail.html', product=product, related_products=related_products)

# Try-on routes
@app.route('/try-on/<int:product_id>', methods=['GET'])
def try_on_page(product_id):
    """Try-on page for a specific product"""
    product = Product.query.get_or_404(product_id)
    # Check if user is logged in and has credits
    has_credits = False
    if current_user.is_authenticated:
        has_credits = current_user.credits > 0
    
    return render_template('try_on.html', product=product, has_credits=has_credits)

@app.route('/try-on', methods=['GET'])
def try_on_generic():
    """Generic try-on page without a specific product"""
    # Check if user is logged in and has credits
    has_credits = False
    if current_user.is_authenticated:
        has_credits = current_user.credits > 0
    
    return render_template('try_on.html', product=None, has_credits=has_credits)

@app.route('/business-try-on', methods=['GET'])
def business_try_on():
    """Business try-on page for creating professional marketing images"""
    # Check if user is logged in and has credits
    has_credits = False
    if current_user.is_authenticated:
        has_credits = current_user.credits > 0
    
    return render_template('business_try_on.html', has_credits=has_credits)

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
        person_path, person_filename = save_uploaded_file(person_image, 'person')
        garment_path, garment_filename = save_uploaded_file(garment_image, 'garment')
        
        # Process the images with Kling AI
        result_filename, message = process_images(person_path, garment_path)
        
        if result_filename:
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
                    person_image_path=person_filename,
                    garment_image_path=garment_filename
                )
                
                db.session.add(try_on_record)
                db.session.commit()
            
            return jsonify({
                "status": "success", 
                "result_url": f"/results/{result_filename}"
            })
        else:
            return jsonify({
                "status": "error",
                "message": message
            }), 500
            
    except Exception as e:
        return jsonify({
            "status": "error", 
            "message": str(e)
        }), 500

@app.route('/api/business-try-on', methods=['POST'])
def business_try_on_api():
    """API endpoint for business virtual try-on"""
    # Ensure user is authorized if logged in (for premium features)
    if current_user.is_authenticated and current_user.credits <= 0:
        return jsonify({
            "status": "error",
            "message": "You have no try-on credits left. Please purchase credits to continue."
        }), 403
    
    # Check if garment image exists in the request
    if 'garment_image' not in request.files:
        return jsonify({
            "status": "error", 
            "message": "Garment image is required"
        }), 400
    
    # Required parameters
    model_id = request.form.get('model_id')
    pose_id = request.form.get('pose_id')
    background_type = request.form.get('background_type')
    background_value = request.form.get('background_value')
    
    if not all([model_id, pose_id, background_type, background_value]):
        return jsonify({
            "status": "error", 
            "message": "Missing required parameters: model_id, pose_id, background_type, or background_value"
        }), 400
    
    garment_image = request.files['garment_image']
    
    # Check if the file is allowed
    if not allowed_file(garment_image.filename):
        return jsonify({
            "status": "error", 
            "message": "Only image files (PNG, JPG, JPEG, GIF) are allowed"
        }), 400
    
    try:
        # Construct the model image path based on selected model and pose
        model_filename = f"model-{model_id}.jpg"
        pose_filename = f"pose-{pose_id}.jpg"
        
        # Build paths to the model and pose images
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'images', 'business', 'models', model_filename)
        pose_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'images', 'business', 'poses', pose_filename)
        
        # If the specific model-pose combination doesn't exist, use a generic model image
        if not os.path.exists(model_path) or not os.path.exists(pose_path):
            model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'images', 'business', 'models', 'model-1.jpg')
            
        # Save garment image to uploads folder
        garment_path, garment_filename = save_uploaded_file(garment_image, 'business_garment')
        
        # Handle different background types
        if background_type == 'color':
            background_path = None  # For solid color backgrounds, we'll handle this in the process_business_images function
        else:  # 'image' type
            background_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'images', 'business', 'backgrounds', background_value)
        
        # Process the images using the Kling AI virtual try-on
        result_filename, message = process_business_images(model_path, garment_path, background_type, background_value)
        
        if result_filename:
            # If user is logged in, deduct a credit and save try-on history
            if current_user.is_authenticated:
                current_user.credits -= 1
                
                # Save try-on history
                try_on_record = TryOnHistory(
                    user_id=current_user.id,
                    product_id=None,  # No specific product here
                    result_path=result_filename,
                    person_image_path=os.path.basename(model_path),
                    garment_image_path=garment_filename
                )
                
                db.session.add(try_on_record)
                db.session.commit()
            
            return jsonify({
                "status": "success", 
                "result_url": f"/results/{result_filename}"
            })
        else:
            return jsonify({
                "status": "error",
                "message": message
            }), 500
            
    except Exception as e:
        logger.error(f"Error in business try-on: {str(e)}")
        return jsonify({
            "status": "error", 
            "message": str(e)
        }), 500
    
@app.route('/privacy-policy')
def privacy_policy():
    """Privacy Policy page"""
    return render_template('privacy_policy.html')

@app.route('/terms-of-service')
def terms_of_service():
    """Terms of Service page"""
    return render_template('terms_of_service.html')

# Serve files
@app.route('/static/<path:path>')
def serve_static(path):
    """Serve static files"""
    return send_from_directory('static', path)

@app.route('/results/<path:filename>')
def serve_result(filename):
    """Serve result images"""
    return send_from_directory(app.config['RESULTS_FOLDER'], filename)

@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    """Serve uploaded images"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.after_request
def after_request(response):
    """Add CORS headers to responses"""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    return response

# Initialize the database if it doesn't exist
def create_initial_data():
    """Create initial data for the database"""
    # Create admin user
    if not User.query.filter_by(email='admin@fashioncore.com').first():
        admin = User(
            username='admin',
            email='admin@fashioncore.com',
            is_admin=True
        )
        admin.set_password('adminpassword')
        db.session.add(admin)
    
    # Create sample products
    if Product.query.count() == 0:
        products = [
            {
                'name': 'Kanchipuram Silk Saree',
                'description': 'Beautiful traditional Kanchipuram silk saree with zari work.',
                'price': 18999.0,
                'image_path': 'samples/silk-saree.jpg',
                'category': 'Saree',
                'brand': 'Pothys'
            },
            {
                'name': 'Designer Anarkali Suit',
                'description': 'Elegant designer Anarkali suit with exquisite embroidery.',
                'price': 12499.0,
                'image_path': 'samples/anarkali.jpg',
                'category': 'Anarkali',
                'brand': 'Meena Bazaar'
            },
            {
                'name': 'Bridal Lehenga Choli',
                'description': 'Stunning bridal lehenga choli with heavy embroidery work.',
                'price': 85000.0,
                'image_path': 'samples/lehenga.jpg',
                'category': 'Lehenga',
                'brand': 'Sabyasachi'
            },
            {
                'name': 'Designer Palazzo Kurti Set',
                'description': 'Stylish designer palazzo kurti set with gota patti work.',
                'price': 4999.0,
                'image_path': 'samples/kurti.jpg',
                'category': 'Kurti',
                'brand': 'W for Woman'
            },
            {
                'name': 'Embellished Sharara Set',
                'description': 'Gorgeous embellished sharara set with sequin work.',
                'price': 22999.0,
                'image_path': 'samples/sharara.jpg',
                'category': 'Sharara',
                'brand': 'Ritu Kumar'
            },
            {
                'name': 'Banarasi Silk Saree',
                'description': 'Classic Banarasi silk saree with gold zari work.',
                'price': 32999.0,
                'image_path': 'samples/banarasi.jpg',
                'category': 'Saree',
                'brand': 'Ekaya'
            }
        ]
        
        for product_data in products:
            product = Product(**product_data)
            db.session.add(product)
    
    db.session.commit()

@app.before_first_request
def initialize_database():
    """Initialize the database before the first request"""
    db.create_all()
    create_initial_data()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)