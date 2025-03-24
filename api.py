from flask import Flask, request, jsonify, send_from_directory, render_template, url_for
from flask_cors import CORS
import os
import jwt
import time
import requests
import json
import base64
import uuid
import cv2
import numpy as np
from datetime import datetime
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure app
app = Flask(__name__)
CORS(app)  # Enable Cross-Origin Resource Sharing

# Configuration
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['RESULTS_FOLDER'] = 'results'
app.config['STATIC_FOLDER'] = 'static'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg'}
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max upload size
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your_secret_key_here')

# API credentials (store these in environment variables in production)
API_KEYS = {
    'demo_client': 'demo_secret',  # Example client credentials
    # Add more client credentials here
}

# KlingAI API credentials
KLING_ACCESS_KEY = os.environ.get('KLING_ACCESS_KEY', '7a3e661ac9f449e1a9416a9ad6aa7617')
KLING_SECRET_KEY = os.environ.get('KLING_SECRET_KEY', '528c39f046024bc284c724457380ec1a')

# Create necessary directories
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RESULTS_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['STATIC_FOLDER'], 'js'), exist_ok=True)
os.makedirs(os.path.join(app.config['STATIC_FOLDER'], 'css'), exist_ok=True)

# In-memory storage (use a database in production)
user_images = {}  # Maps emails to image paths
product_images = {}  # Maps product_ids to image paths
try_on_results = {}  # Maps (email, product_id) to result paths

# Helper functions
def allowed_file(filename):
    """Check if a file has an allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def authenticate():
    """Verify API authentication"""
    auth = request.headers.get('Authorization')
    if not auth or not auth.startswith('Bearer '):
        return False, "Missing or invalid Authorization header"
    
    try:
        # Format: "Bearer client_id:client_secret"
        credentials = auth.split(' ')[1].split(':')
        if len(credentials) != 2:
            return False, "Invalid credentials format"
        
        client_id, client_secret = credentials
        
        if client_id not in API_KEYS or API_KEYS[client_id] != client_secret:
            return False, "Invalid client credentials"
        
        return True, client_id
    except Exception as e:
        return False, f"Authentication error: {str(e)}"

# KlingAI API client
class KlingAIClient:
    def __init__(self):
        self.access_key = KLING_ACCESS_KEY
        self.secret_key = KLING_SECRET_KEY
        self.base_url = "https://api.klingai.com"
    
    def _generate_jwt_token(self):
        """Generate a JWT token for KlingAI API authentication"""
        headers = {
            "alg": "HS256",
            "typ": "JWT"
        }
        payload = {
            "iss": self.access_key,
            "exp": int(time.time()) + 1800,  # 30 minutes
            "nbf": int(time.time()) - 5  # 5 seconds ago
        }
        return jwt.encode(payload, self.secret_key, headers=headers)
    
    def _get_headers(self):
        """Get the headers for KlingAI API requests"""
        return {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {self._generate_jwt_token()}"
        }
    
    def try_on(self, person_img_path, garment_img_path, seed=None):
        """Use KlingAI's Virtual Try-on API to generate a try-on image"""
        try:
            # Read images
            with open(person_img_path, 'rb') as f:
                person_img_data = f.read()
            with open(garment_img_path, 'rb') as f:
                garment_img_data = f.read()
            
            # Encode images to base64
            encoded_person = base64.b64encode(person_img_data).decode('utf-8')
            encoded_garment = base64.b64encode(garment_img_data).decode('utf-8')
            
            # Prepare request data
            data = {
                "model_name": "kolors-virtual-try-on-v1-5",  # Using the improved V1.5 model
                "cloth_image": encoded_garment,
                "human_image": encoded_person
            }
            
            # Add seed if provided
            if seed is not None:
                data["seed"] = seed
            
            # Submit task
            print(f"Submitting try-on task to KlingAI API")
            response = requests.post(
                f"{self.base_url}/v1/images/kolors-virtual-try-on", 
                headers=self._get_headers(),
                json=data,
                timeout=30
            )
            
            if response.status_code != 200:
                print(f"API error: {response.status_code} - {response.text}")
                return None, f"API error: {response.status_code} - {response.text}"
            
            result = response.json()
            task_id = result['data']['task_id']
            print(f"Task submitted with ID: {task_id}")
            
            # Poll for result
            max_attempts = 30
            for attempt in range(max_attempts):
                time.sleep(3)  # Wait 3 seconds between checks
                
                check_url = f"{self.base_url}/v1/images/kolors-virtual-try-on/{task_id}"
                print(f"Checking task status (attempt {attempt+1}/{max_attempts})")
                check_response = requests.get(check_url, headers=self._get_headers(), timeout=20)
                
                if check_response.status_code != 200:
                    print(f"Error checking status: {check_response.status_code}")
                    continue
                
                check_result = check_response.json()
                status = check_result['data']['task_status']
                
                if status == "succeed":
                    # Get result image URL
                    output_url = check_result['data']['task_result']['images'][0]['url']
                    print(f"Try-on successful! Result URL: {output_url}")
                    return output_url, "Success"
                elif status == "failed":
                    error_msg = check_result['data']['task_status_msg']
                    print(f"Task failed: {error_msg}")
                    return None, f"Task failed: {error_msg}"
            
            return None, "Timeout waiting for result"
            
        except Exception as e:
            print(f"Error in try_on: {str(e)}")
            return None, f"Error: {str(e)}"

# API Routes
@app.route('/')
def index():
    """Landing page for the API"""
    return render_template('index.html')

@app.route('/demo')
def demo():
    """Demo product page"""
    return render_template('demo.html')

@app.route('/api/try-on', methods=['POST'])
def try_on():
    """Process try-on request from website (non-API endpoint)"""
    try:
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
                "message": "Only image files (PNG, JPG, JPEG) are allowed"
            }), 400
        
        # Save uploaded files
        person_path = os.path.join(app.config['UPLOAD_FOLDER'], 
                                   f"person_{uuid.uuid4().hex}.{person_image.filename.rsplit('.', 1)[1].lower()}")
        garment_path = os.path.join(app.config['UPLOAD_FOLDER'], 
                                    f"garment_{uuid.uuid4().hex}.{garment_image.filename.rsplit('.', 1)[1].lower()}")
        
        person_image.save(person_path)
        garment_image.save(garment_path)
        
        # Process the images with KlingAI
        kling_client = KlingAIClient()
        result_url, message = kling_client.try_on(person_path, garment_path)
        
        if not result_url:
            return jsonify({
                "status": "error", 
                "message": message
            }), 500
        
        # Download the result image
        result_filename = f"result_{uuid.uuid4().hex}.jpg"
        result_path = os.path.join(app.config['RESULTS_FOLDER'], result_filename)
        
        try:
            # Download and save the result image
            response = requests.get(result_url, timeout=30)
            if response.status_code == 200:
                with open(result_path, 'wb') as f:
                    f.write(response.content)
            else:
                return jsonify({
                    "status": "error", 
                    "message": f"Failed to download result image: {response.status_code}"
                }), 500
        except Exception as e:
            return jsonify({
                "status": "error", 
                "message": f"Error saving result: {str(e)}"
            }), 500
        
        # Return the result URL
        return jsonify({
            "status": "success", 
            "result_url": url_for('serve_result', filename=result_filename)
        })
            
    except Exception as e:
        return jsonify({
            "status": "error", 
            "message": str(e)
        }), 500

# API Endpoints for external integration
@app.route('/upload/person', methods=['POST'])
def upload_person():
    """Upload person image API endpoint"""
    # Authenticate request
    auth_success, auth_message = authenticate()
    if not auth_success:
        return jsonify({'message': auth_message}), 401
    
    # Check for required parameters
    if 'person_image' not in request.files:
        return jsonify({'message': 'No person_image part'}), 400
    
    email = request.form.get('email')
    if not email:
        return jsonify({'message': 'Email is required'}), 400
    
    # Process the file
    file = request.files['person_image']
    if file.filename == '':
        return jsonify({'message': 'No selected file'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(f"person_{email.replace('@', '_')}_{uuid.uuid4().hex}.{file.filename.rsplit('.', 1)[1].lower()}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Save the file path for this email
        user_images[email] = filepath
        
        return jsonify({
            'message': 'Person image uploaded successfully',
            'email': email,
            'file_path': filepath
        })
    
    return jsonify({'message': 'Invalid file type'}), 400

@app.route('/upload/garment', methods=['POST'])
def upload_garment():
    """Upload garment image API endpoint"""
    # Authenticate request
    auth_success, auth_message = authenticate()
    if not auth_success:
        return jsonify({'message': auth_message}), 401
    
    # Check for required parameters
    if 'garment_image' not in request.files:
        return jsonify({'message': 'No garment_image part'}), 400
    
    product_id = request.form.get('product_id')
    if not product_id:
        return jsonify({'message': 'Product ID is required'}), 400
    
    # Process the file
    file = request.files['garment_image']
    if file.filename == '':
        return jsonify({'message': 'No selected file'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(f"garment_{product_id}_{uuid.uuid4().hex}.{file.filename.rsplit('.', 1)[1].lower()}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Save the file path for this product
        product_images[product_id] = filepath
        
        return jsonify({
            'message': 'Garment image uploaded successfully',
            'product_id': product_id,
            'file_path': filepath
        })
    
    return jsonify({'message': 'Invalid file type'}), 400

@app.route('/run-tryon', methods=['POST'])
def run_tryon():
    """Run try-on process API endpoint"""
    # Authenticate request
    auth_success, auth_message = authenticate()
    if not auth_success:
        return jsonify({'message': auth_message}), 401
    
    # Check for required parameters
    data = request.json
    email = data.get('email')
    product_id = data.get('product_id')
    seed = data.get('seed')
    
    if not email or not product_id:
        return jsonify({'message': 'Email and product_id are required'}), 400
    
    # Check if we have images for this email and product
    if email not in user_images:
        return jsonify({'message': f'No person image found for email: {email}'}), 404
    
    if product_id not in product_images:
        return jsonify({'message': f'No garment image found for product_id: {product_id}'}), 404
    
    # Process try-on
    kling_client = KlingAIClient()
    result_url, message = kling_client.try_on(
        user_images[email], 
        product_images[product_id],
        seed
    )
    
    if not result_url:
        return jsonify({'message': message}), 500
    
    # Download the result image
    result_filename = f"result_{email.replace('@', '_')}_{product_id}_{uuid.uuid4().hex}.jpg"
    result_path = os.path.join(app.config['RESULTS_FOLDER'], result_filename)
    
    try:
        # Download and save the result image
        response = requests.get(result_url, timeout=30)
        if response.status_code == 200:
            with open(result_path, 'wb') as f:
                f.write(response.content)
            
            # Save the result path
            try_on_results[(email, product_id)] = result_path
            
            return jsonify({
                'message': 'Try-on successful',
                'email': email,
                'product_id': product_id,
                'status': 'completed',
                'result_id': f"{email}_{product_id}"
            })
        else:
            return jsonify({'message': f'Failed to download result image: {response.status_code}'}), 500
    except Exception as e:
        return jsonify({'message': f'Error saving result: {str(e)}'}), 500

@app.route('/preview-result', methods=['GET'])
def preview_result():
    """Get try-on result API endpoint"""
    # Authenticate request
    auth_success, auth_message = authenticate()
    if not auth_success:
        return jsonify({'message': auth_message}), 401
    
    # Check for required parameters
    email = request.args.get('email')
    product_id = request.args.get('product_id')
    
    if not email or not product_id:
        return jsonify({'message': 'Email and product_id are required'}), 400
    
    # Check if we have a result for this combination
    if (email, product_id) not in try_on_results:
        return jsonify({'message': 'No result found for this email and product_id'}), 404
    
    result_path = try_on_results[(email, product_id)]
    result_filename = os.path.basename(result_path)
    
    # Construct URLs for viewing and downloading
    host_url = request.host_url.rstrip('/')
    image_url = f"{host_url}/results/{result_filename}"
    download_url = f"{host_url}/download/{result_filename}"
    
    return jsonify({
        'email': email,
        'product_id': product_id,
        'image_url': image_url,
        'download_url': download_url
    })

# File serving routes
@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files"""
    return send_from_directory(app.config['STATIC_FOLDER'], filename)

@app.route('/results/<filename>')
def serve_result(filename):
    """Serve result images"""
    return send_from_directory(app.config['RESULTS_FOLDER'], filename)

@app.route('/download/<filename>')
def download_file(filename):
    """Download result images"""
    return send_from_directory(
        app.config['RESULTS_FOLDER'], 
        filename, 
        as_attachment=True
    )

# Healthcheck endpoint
@app.route('/healthcheck')
def healthcheck():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'uptime': time.time()
    })

# Main entry point
if __name__ == '__main__':
    # Copy static files (in real project you'd use a build process)
    print("Setting up static files...")
    
    # Ensure the static directory exists
    os.makedirs(os.path.join(app.config['STATIC_FOLDER'], 'js'), exist_ok=True)
    
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('DEBUG', 'True').lower() == 'true'
    
    print(f"Starting server on port {port}, debug mode: {debug}")
    app.run(debug=debug, host='0.0.0.0', port=port)