from flask import Flask, request, jsonify, send_from_directory, render_template, url_for
from flask_restx import Api, Resource, fields, reqparse
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename
import jwt
import time
import os
import requests
import json
import base64
import uuid
import cv2
import numpy as np
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['RESULTS_FOLDER'] = 'results'
app.config['STATIC_FOLDER'] = 'static'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg'}
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max upload size
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your_secret_key_here')

# Create directories if they don't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['RESULTS_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['STATIC_FOLDER'], 'js'), exist_ok=True)

# API credentials (store these securely in production)
API_KEYS = {
    'demo_client': 'demo_secret',  # Example credentials
    # Add more client credentials here
}

# KlingAI API credentials
KLING_ACCESS_KEY = os.environ.get('KLING_ACCESS_KEY', '7a3e661ac9f449e1a9416a9ad6aa7617')
KLING_SECRET_KEY = os.environ.get('KLING_SECRET_KEY', '528c39f046024bc284c724457380ec1a')

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

# Setup Flask-RestX
authorizations = {
    'apikey': {
        'type': 'apiKey',
        'in': 'header',
        'name': 'Authorization',
        'description': 'Format: Bearer client_id:client_secret'
    }
}

api = Api(app, version='1.0', title='Virtual Try-On API',
          description='API for virtual clothing try-on using KlingAI technology',
          doc='/swagger/',
          authorizations=authorizations,
          security='apikey')

# Define namespaces
ns = api.namespace('api', description='Virtual Try-On operations')

# Models for Swagger documentation
person_upload_model = api.model('PersonUpload', {
    'email': fields.String(required=True, description='User email address')
})

garment_upload_model = api.model('GarmentUpload', {
    'product_id': fields.String(required=True, description='Product identifier')
})

tryon_model = api.model('TryOn', {
    'email': fields.String(required=True, description='User email address'),
    'product_id': fields.String(required=True, description='Product identifier'),
    'seed': fields.Integer(required=False, description='Random seed for try-on generation')
})

result_model = api.model('Result', {
    'email': fields.String(required=True, description='User email address'),
    'product_id': fields.String(required=True, description='Product identifier'),
    'image_url': fields.String(description='URL to view the try-on result'),
    'download_url': fields.String(description='URL to download the try-on result')
})

# File upload parsers
upload_parser = reqparse.RequestParser()
upload_parser.add_argument('email', type=str, required=True, help='User email address')
upload_parser.add_argument('person_image', type=FileStorage, location='files', required=True, help='Person image file')

garment_parser = reqparse.RequestParser()
garment_parser.add_argument('product_id', type=str, required=True, help='Product identifier')
garment_parser.add_argument('garment_image', type=FileStorage, location='files', required=True, help='Garment image file')

# API Endpoints
@ns.route('/upload/person')
class PersonUpload(Resource):
    @api.doc('upload_person', parser=upload_parser, security='apikey')
    @api.response(200, 'Success')
    @api.response(400, 'Invalid input')
    @api.response(401, 'Authentication error')
    def post(self):
        """Upload a person image for virtual try-on"""
        # Authenticate request
        auth_success, auth_message = authenticate()
        if not auth_success:
            api.abort(401, auth_message)
        
        args = upload_parser.parse_args()
        email = args['email']
        file = args['person_image']
        
        if not email:
            api.abort(400, 'Email is required')
        
        if file.filename == '':
            api.abort(400, 'No selected file')
        
        if file and allowed_file(file.filename):
            filename = secure_filename(f"person_{email.replace('@', '_')}_{uuid.uuid4().hex}.{file.filename.rsplit('.', 1)[1].lower()}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Save the file path for this email
            user_images[email] = filepath
            
            return {
                'message': 'Person image uploaded successfully',
                'email': email,
                'file_path': filepath
            }
        
        api.abort(400, 'Invalid file type')

@ns.route('/upload/garment')
class GarmentUpload(Resource):
    @api.doc('upload_garment', parser=garment_parser, security='apikey')
    @api.response(200, 'Success')
    @api.response(400, 'Invalid input')
    @api.response(401, 'Authentication error')
    def post(self):
        """Upload a garment image for virtual try-on"""
        # Authenticate request
        auth_success, auth_message = authenticate()
        if not auth_success:
            api.abort(401, auth_message)
        
        args = garment_parser.parse_args()
        product_id = args['product_id']
        file = args['garment_image']
        
        if not product_id:
            api.abort(400, 'Product ID is required')
        
        if file.filename == '':
            api.abort(400, 'No selected file')
        
        if file and allowed_file(file.filename):
            filename = secure_filename(f"garment_{product_id}_{uuid.uuid4().hex}.{file.filename.rsplit('.', 1)[1].lower()}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Save the file path for this product
            product_images[product_id] = filepath
            
            return {
                'message': 'Garment image uploaded successfully',
                'product_id': product_id,
                'file_path': filepath
            }
        
        api.abort(400, 'Invalid file type')

@ns.route('/run-tryon')
class RunTryOn(Resource):
    @api.doc('run_tryon', security='apikey')
    @api.expect(tryon_model)
    @api.response(200, 'Success')
    @api.response(400, 'Invalid input')
    @api.response(401, 'Authentication error')
    @api.response(404, 'Images not found')
    @api.response(500, 'Processing error')
    def post(self):
        """Run the virtual try-on process"""
        # Authenticate request
        auth_success, auth_message = authenticate()
        if not auth_success:
            api.abort(401, auth_message)
        
        data = request.json
        email = data.get('email')
        product_id = data.get('product_id')
        seed = data.get('seed')
        
        if not email or not product_id:
            api.abort(400, 'Email and product_id are required')
        
        # Check if we have images for this email and product
        if email not in user_images:
            api.abort(404, f'No person image found for email: {email}')
        
        if product_id not in product_images:
            api.abort(404, f'No garment image found for product_id: {product_id}')
        
        # Process try-on
        kling_client = KlingAIClient()
        result_url, message = kling_client.try_on(
            user_images[email], 
            product_images[product_id],
            seed
        )
        
        if not result_url:
            api.abort(500, message)
        
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
                
                return {
                    'message': 'Try-on successful',
                    'email': email,
                    'product_id': product_id,
                    'status': 'completed',
                    'result_id': f"{email}_{product_id}"
                }
            else:
                api.abort(500, f'Failed to download result image: {response.status_code}')
        except Exception as e:
            api.abort(500, f'Error saving result: {str(e)}')

@ns.route('/preview-result')
@api.doc(params={'email': 'User email address', 'product_id': 'Product identifier'})
class PreviewResult(Resource):
    @api.doc('preview_result', security='apikey')
    @api.response(200, 'Success', result_model)
    @api.response(400, 'Invalid input')
    @api.response(401, 'Authentication error')
    @api.response(404, 'Result not found')
    def get(self):
        """Get the try-on result image"""
        # Authenticate request
        auth_success, auth_message = authenticate()
        if not auth_success:
            api.abort(401, auth_message)
        
        email = request.args.get('email')
        product_id = request.args.get('product_id')
        
        if not email or not product_id:
            api.abort(400, 'Email and product_id are required')
        
        # Check if we have a result for this combination
        if (email, product_id) not in try_on_results:
            api.abort(404, 'No result found for this email and product_id')
        
        result_path = try_on_results[(email, product_id)]
        result_filename = os.path.basename(result_path)
        
        # Construct URLs for viewing and downloading
        host_url = request.host_url.rstrip('/')
        image_url = f"{host_url}/results/{result_filename}"
        download_url = f"{host_url}/download/{result_filename}"
        
        return {
            'email': email,
            'product_id': product_id,
            'image_url': image_url,
            'download_url': download_url
        }

# Routes for file serving and HTML templates
@app.route('/')
def index():
    """Landing page that redirects to Swagger UI"""
    return render_template('index1.html')

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

@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files"""
    return send_from_directory(app.config['STATIC_FOLDER'], filename)

# For local try-on (not through API)
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

# Main entry point
if __name__ == '__main__':
    # Make sure directories exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['RESULTS_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(app.config['STATIC_FOLDER'], 'js'), exist_ok=True)
    
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('DEBUG', 'True').lower() == 'true'
    
    print(f"Starting server on port {port}, debug mode: {debug}")
    print(f"Swagger UI available at: http://localhost:{port}/swagger/")
    app.run(debug=debug, host='0.0.0.0', port=port)