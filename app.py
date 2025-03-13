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
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import requests
import base64

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
app.config['HUGGINGFACE_URL'] = "https://huggingface.co/spaces/Kwai-Kolors/Kolors-Virtual-Try-On"
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['RESULTS_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max upload size
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

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

# Define selectors for Selenium
SELECTORS = {
    # Person image upload button
    'person_button': {
        'css': "button.svelte-1x5qevo",
        'xpath': "(//button[contains(@class, 'center')])[1]"
    },
    # Garment image upload button
    'garment_button': {
        'css': None,
        'xpath': "(//button[contains(@class, 'center')])[2]"
    },
    # Run button
    'run_button': {
        'css': "#button",
        'xpath': "//button[@id='button']"
    },
    # File input elements
    'file_input': {
        'css': "input[type='file']",
        'xpath': "//input[@type='file']"
    },
    # Result image
    'result_image': {
        'css': ".image-frame.svelte-1p15vfy > img.svelte-1pijsyv",
        'css_alt': "div:has-text('Result') img.svelte-1pijsyv",
        'xpath': "//div[contains(text(), 'Result')]//img[@class='svelte-1pijsyv']"
    }
}

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
    return filepath

def setup_driver():
    """Set up and return a Selenium webdriver with Chrome."""
    logger.info("Setting up Chrome driver")
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--start-maximized')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-extensions')
    
    try:
        driver = webdriver.Chrome(options=options)
        logger.info("Chrome driver setup complete")
        return driver
    except Exception as e:
        logger.error(f"Error setting up Chrome driver: {str(e)}")
        raise

def save_screenshot(driver, filename):
    """Save a screenshot for debugging purposes"""
    filepath = os.path.join(app.config['RESULTS_FOLDER'], filename)
    driver.save_screenshot(filepath)
    logger.info(f"Screenshot saved to {filepath}")
    return filepath

def check_for_uploading_text(driver):
    """Check if 'Uploading' text is present on the page"""
    page_source = driver.page_source.lower()
    upload_indicators = ["uploading", "upload in progress", "processing", "please wait"]
    return any(indicator in page_source for indicator in upload_indicators)

def check_upload_filenames_visible(driver, person_filename, garment_filename):
    """Check if both uploaded filenames are visible on the page"""
    person_base = "person_" if "_" not in person_filename else person_filename.split("_")[0]
    garment_base = "garment_" if "_" not in garment_filename else garment_filename.split("_")[0]
    page_source = driver.page_source
    return person_base in page_source and garment_base in page_source

def wait_for_upload_completion(driver, person_filename, garment_filename, result_id):
    """Wait for both uploads to complete"""
    logger.info("Waiting for uploads to complete")
    start_time = time.time()
    max_wait_time = 120  # 2 minutes timeout
    
    while time.time() - start_time < max_wait_time:
        uploading = check_for_uploading_text(driver)
        if not uploading and check_upload_filenames_visible(driver, person_filename, garment_filename):
            logger.info("Uploads appear to be complete")
            save_screenshot(driver, f"uploads_complete_{result_id}.png")
            return True
        logger.info("Uploads still in progress, waiting...")
        time.sleep(5)
    
    logger.warning("Timeout waiting for uploads to complete")
    return False

def is_run_button_enabled(run_button):
    """Check if the Run button is enabled"""
    if not run_button:
        return False
    try:
        disabled = run_button.get_attribute('disabled')
        if disabled and disabled.lower() in ['true', '1']:
            return False
        classes = run_button.get_attribute('class') or ""
        has_disabled_class = "disabled" in classes
        opacity = run_button.value_of_css_property('opacity')
        pointer_events = run_button.value_of_css_property('pointer-events')
        button_text = run_button.text.lower()
        return (not disabled and not has_disabled_class and opacity != "0.5" 
                and "run" in button_text and pointer_events != "none")
    except:
        return False

def wait_for_run_button_enabled(driver, result_id):
    """Wait for Run button to be enabled after uploads complete"""
    logger.info("Waiting for Run button to be enabled")
    start_time = time.time()
    max_wait_time = 120  # 2 minute timeout
    
    while time.time() - start_time < max_wait_time:
        try:
            run_button = None
            try:
                run_button = driver.find_element(By.CSS_SELECTOR, SELECTORS['run_button']['css'])
            except:
                try:
                    run_button = driver.find_element(By.XPATH, SELECTORS['run_button']['xpath'])
                except:
                    pass
            
            if run_button:
                if is_run_button_enabled(run_button):
                    logger.info("Run button is enabled and ready to click")
                    save_screenshot(driver, f"run_button_enabled_{result_id}.png")
                    return run_button
                else:
                    logger.info("Run button is still disabled, waiting...")
            else:
                logger.info("Run button not found, waiting...")
            
            time.sleep(3)
        except Exception as e:
            logger.warning(f"Error checking run button: {str(e)}")
            time.sleep(3)
    
    logger.warning("Timeout waiting for Run button to be enabled")
    return None

def wait_for_result_image(driver, result_id):
    """Wait for the result image to appear in the Result section"""
    logger.info("Waiting for result image to appear")
    start_time = time.time()
    max_wait_time = 180  # 3 minutes timeout
    
    while time.time() - start_time < max_wait_time:
        try:
            result_image = None
            try:
                result_image = driver.find_element(By.CSS_SELECTOR, SELECTORS['result_image']['css'])
            except:
                try:
                    result_image = driver.find_element(By.CSS_SELECTOR, SELECTORS['result_image']['css_alt'])
                except:
                    try:
                        result_image = driver.find_element(By.XPATH, SELECTORS['result_image']['xpath'])
                    except:
                        pass
            
            if result_image:
                src = result_image.get_attribute('src')
                if src and len(src) > 10:
                    logger.info(f"Result image found with src: {src[:50]}...")
                    save_screenshot(driver, f"result_image_found_{result_id}.png")
                    return result_image
                else:
                    logger.info("Result image found but src is empty or invalid")
            
            logger.info("Result image not found yet, waiting...")
            time.sleep(10)
        except Exception as e:
            logger.warning(f"Error checking for result image: {str(e)}")
            time.sleep(10)
    
    logger.warning("Timeout waiting for result image")
    return None

def download_result_image(driver, result_id, result_file_path):
    """Download the result image from the Result section"""
    logger.info("Attempting to download result image")
    
    try:
        result_image = wait_for_result_image(driver, result_id)
        
        if not result_image:
            logger.error("Could not find result image element")
            return False
        
        src = result_image.get_attribute('src')
        if not src:
            logger.error("Result image has no src attribute")
            return False
        
        if src.startswith('data:image'):
            try:
                header, data = src.split(',', 1)
                image_data = base64.b64decode(data)
                with open(result_file_path, 'wb') as f:
                    f.write(image_data)
                logger.info(f"Result image saved to {result_file_path} (data URL)")
                return True
            except Exception as e:
                logger.error(f"Error saving data URL image: {str(e)}")
                return False
        elif src.startswith('http'):
            try:
                response = requests.get(src, timeout=30)
                if response.status_code == 200:
                    with open(result_file_path, 'wb') as f:
                        f.write(response.content)
                    logger.info(f"Result image saved to {result_file_path} (HTTP URL)")
                    return True
                else:
                    logger.error(f"HTTP error {response.status_code} downloading image")
                    return False
            except Exception as e:
                logger.error(f"Error downloading HTTP URL image: {str(e)}")
                return False
        else:
            logger.error(f"Unsupported image src format: {src[:20]}...")
            return False
    except Exception as e:
        logger.error(f"Error in download_result_image: {str(e)}")
        return False

def process_images(person_image_path, garment_image_path):
    """
    Process the images using the HuggingFace demo and return the result image.
    
    Args:
        person_image_path: Path to the person image file
        garment_image_path: Path to the garment image file
        
    Returns:
        Path to the result image or error message
    """
    driver = None
    result_id = f"{uuid.uuid4().hex}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    result_file_path = os.path.join(app.config['RESULTS_FOLDER'], f"result_{result_id}.png")
    
    try:
        driver = setup_driver()
        
        # Navigate to HuggingFace
        logger.info(f"Navigating to {app.config['HUGGINGFACE_URL']}")
        driver.get(app.config['HUGGINGFACE_URL'])
        
        # Wait for page to load
        logger.info("Waiting for page to load")
        time.sleep(20)
        
        # Check for iframes and switch if present
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        if len(iframes) > 0:
            logger.info("Switching to first iframe")
            driver.switch_to.frame(iframes[0])
        
        # Find file inputs
        file_inputs = driver.find_elements(By.CSS_SELECTOR, SELECTORS['file_input']['css'])
        if not file_inputs or len(file_inputs) < 2:
            file_inputs = driver.find_elements(By.XPATH, SELECTORS['file_input']['xpath'])
        
        if len(file_inputs) < 2:
            return {"status": "error", "message": "Could not find file inputs for uploading images"}
        
        # Extract filenames for verification
        person_filename = os.path.basename(person_image_path)
        garment_filename = os.path.basename(garment_image_path)
        
        # Upload person image
        logger.info(f"Uploading person image from {person_image_path}")
        try:
            file_inputs[0].send_keys(os.path.abspath(person_image_path))
            logger.info("Person image uploaded")
            time.sleep(5)
        except Exception as e:
            logger.error(f"Error uploading person image: {str(e)}")
            return {"status": "error", "message": f"Could not upload person image: {str(e)}"}
        
        # Upload garment image
        logger.info(f"Uploading garment image from {garment_image_path}")
        try:
            file_inputs[1].send_keys(os.path.abspath(garment_image_path))
            logger.info("Garment image uploaded")
            time.sleep(5)
        except Exception as e:
            logger.error(f"Error uploading garment image: {str(e)}")
            return {"status": "error", "message": f"Could not upload garment image: {str(e)}"}
        
        # Wait for uploads to complete
        if not wait_for_upload_completion(driver, person_filename, garment_filename, result_id):
            logger.warning("Upload completion check timed out, will proceed with caution")
        
        # Wait for Run button to be enabled
        run_button = wait_for_run_button_enabled(driver, result_id)
        if not run_button:
            return {"status": "error", "message": "Could not find enabled Run button"}
        
        # Click run button
        logger.info("Clicking run button")
        try:
            run_button.click()
            logger.info("Run button clicked successfully")
        except Exception as e:
            try:
                # Try using JavaScript to click
                driver.execute_script("arguments[0].click();", run_button)
                logger.info("Run button clicked using JavaScript")
            except Exception as js_e:
                logger.error(f"JavaScript click also failed: {str(js_e)}")
                return {"status": "error", "message": "Could not click run button"}
        
        # Wait for processing and download the result image
        logger.info("Waiting for processing and downloading result")
        if download_result_image(driver, result_id, result_file_path):
            logger.info(f"Successfully downloaded result image to {result_file_path}")
            return {"status": "success", "result_path": result_file_path}
        else:
            # Fallback: Take a screenshot as the result
            logger.warning("Failed to download result image, taking screenshot as fallback")
            full_page_screenshot = os.path.join(app.config['RESULTS_FOLDER'], f"fallback_result_{result_id}.png")
            driver.save_screenshot(full_page_screenshot)
            return {"status": "success", "result_path": full_page_screenshot, "is_fallback": True}
        
    except Exception as e:
        logger.error(f"Error during image processing: {str(e)}")
        return {"status": "error", "message": str(e)}
    
    finally:
        if driver:
            logger.info("Closing Chrome driver")
            driver.quit()

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
                    garment_image_path=os.path.basename(garment_path)
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

# Shopping cart routes
@app.route('/cart')
def cart():
    """Shopping cart page"""
    if not current_user.is_authenticated:
        flash('Please log in to view your cart', 'warning')
        return redirect(url_for('login'))
        
    return render_template('cart.html')

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    """Checkout page"""
    if request.method == 'POST':
        # Process checkout (Stripe integration would go here)
        flash('Your order has been placed!', 'success')
        return redirect(url_for('index'))
        
    return render_template('checkout.html')

# Admin routes
@app.route('/admin')
@login_required
def admin_dashboard():
    """Admin dashboard"""
    if not current_user.is_admin:
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('index'))
        
    return render_template('admin/dashboard.html')

@app.route('/admin/products')
@login_required
def admin_products():
    """Admin products management"""
    if not current_user.is_admin:
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('index'))
        
    products = Product.query.all()
    return render_template('admin/products.html', products=products)

@app.route('/admin/orders')
@login_required
def admin_orders():
    """Admin orders management"""
    if not current_user.is_admin:
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('index'))
        
    orders = Order.query.all()
    return render_template('admin/orders.html', orders=orders)

@app.route('/admin/users')
@login_required
def admin_users():
    """Admin users management"""
    if not current_user.is_admin:
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('index'))
        
    users = User.query.all()
    return render_template('admin/users.html', users=users)

# API documentation
@app.route('/api/docs')
def api_docs():
    """API documentation page"""
    return render_template('api_docs.html')

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
    app.run(debug=True, host='127.0.0.1', port=5001)