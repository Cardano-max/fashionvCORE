from fastapi import FastAPI, File, UploadFile, HTTPException, Form, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import cv2
import numpy as np
import time
import jwt
import uuid
import logging
import random
from typing import Optional, Dict, Any, Union, Tuple
import requests
import base64
from pathlib import Path
import shutil

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create app
app = FastAPI(
    title="Virtual Try-On API",
    description="API for virtual try-on using Kling AI",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Constants
MAX_SEED = 999999
BASE_DIR = Path(__file__).resolve().parent

# Create directories if they don't exist
UPLOAD_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

# Mount static files directory
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Global storage for user images
user_images = {}  # Format: {session_id: {'person': image_path, 'garment': image_path}}
user_results = {}  # Format: {session_id: {'result_url': url}}

class KlingAIClient:
    def __init__(self):
        self.access_key = "7a3e661ac9f449e1a9416a9ad6aa7617"
        self.secret_key = "528c39f046024bc284c724457380ec1a"
        self.base_url = "https://api.klingai.com"
        self.logger = logging.getLogger(__name__)
    
    def _generate_jwt_token(self) -> str:
        headers = {
            "alg": "HS256",
            "typ": "JWT"
        }
        payload = {
            "iss": self.access_key,
            "exp": int(time.time()) + 1800,
            "nbf": int(time.time()) - 5
        }
        return jwt.encode(payload, self.secret_key, headers=headers)
    
    def _get_headers(self) -> Dict[str, str]:
        return {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {self._generate_jwt_token()}"
        }
    
    def try_on(self, person_img: np.ndarray, garment_img: np.ndarray, seed: int) -> Tuple[np.ndarray, str]:
        """
        Use the Kling AI's Virtual Try-on API to generate a try-on image.
        
        Args:
            person_img: The person's image
            garment_img: The garment image
            seed: Random seed for generation
            
        Returns:
            The resulting image and status message
        """
        if person_img is None or garment_img is None:
            raise ValueError("Empty image")
            
        # Encode images
        encoded_person = cv2.imencode('.jpg', cv2.cvtColor(person_img, cv2.COLOR_RGB2BGR))[1]
        encoded_person = base64.b64encode(encoded_person.tobytes()).decode('utf-8')
        
        encoded_garment = cv2.imencode('.jpg', cv2.cvtColor(garment_img, cv2.COLOR_RGB2BGR))[1]
        encoded_garment = base64.b64encode(encoded_garment.tobytes()).decode('utf-8')

        # Submit task using the improved V1.5 model
        url = f"{self.base_url}/v1/images/kolors-virtual-try-on"
        data = {
            "model_name": "kolors-virtual-try-on-v1-5",  # Using the improved V1.5 model
            "cloth_image": encoded_garment,
            "human_image": encoded_person,
            "seed": seed
        }

        try:
            self.logger.info("Making API request to Kling AI Virtual Try-on service")
            response = requests.post(
                url, 
                headers=self._get_headers(),
                json=data,
                timeout=50
            )
            
            if response.status_code == 429:
                error_msg = "Sorry, our service is currently at capacity. Please try again in a few minutes."
                self.logger.error(f"API rate limit exceeded: {response.text}")
                return None, error_msg
                
            if response.status_code != 200:
                error_msg = f"Error: API returned status code {response.status_code}"
                self.logger.error(f"API error: {response.text}")
                return None, error_msg
            
            result = response.json()
            task_id = result['data']['task_id']
            
            # Wait for result
            self.logger.info(f"Task submitted successfully. Task ID: {task_id}")
            self.logger.info("Waiting for try-on result...")
            
            # Initial wait
            time.sleep(9)
            
            for attempt in range(12):
                try:
                    url = f"{self.base_url}/v1/images/kolors-virtual-try-on/{task_id}"
                    response = requests.get(url, headers=self._get_headers(), timeout=20)
                    
                    if response.status_code != 200:
                        self.logger.error(f"Error checking task status: {response.text}")
                        time.sleep(1)
                        continue
                    
                    result = response.json()
                    status = result['data']['task_status']
                    
                    if status == "succeed":
                        output_url = result['data']['task_result']['images'][0]['url']
                        self.logger.info(f"Try-on successful! Result URL: {output_url}")
                        
                        img_response = requests.get(output_url)
                        img_response.raise_for_status()
                        
                        nparr = np.frombuffer(img_response.content, np.uint8)
                        result_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        result_img = cv2.cvtColor(result_img, cv2.COLOR_BGR2RGB)
                        return result_img, "Success"
                    elif status == "failed":
                        error_msg = f"Sorry, we couldn't create the try-on image. {result['data']['task_status_msg']}"
                        self.logger.error(f"Task failed: {result['data']['task_status_msg']}")
                        return None, error_msg
                    else:
                        self.logger.info(f"Task status: {status}. Waiting...")
                        
                except requests.exceptions.ReadTimeout:
                    self.logger.warning(f"Timeout on attempt {attempt+1}/12. Retrying...")
                    if attempt == 11:
                        return None, "Sorry, the try-on is taking longer than expected. Please try again."
                        
                time.sleep(1)
                
            return None, "The try-on is taking too long. Please try again later."
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Sorry, we're having trouble connecting to our service. Please try again later."
            self.logger.error(f"API error: {str(e)}")
            return None, error_msg
        except Exception as e:
            error_msg = f"Sorry, something went wrong. Please try again later."
            self.logger.error(f"Unexpected error: {str(e)}")
            return None, error_msg

def generate_unique_filename(prefix="image"):
    """Generate a unique filename using timestamp and UUID"""
    timestamp = int(time.time())
    unique_id = str(uuid.uuid4())[:8]
    return f"{prefix}_{timestamp}_{unique_id}.jpg"

def save_uploaded_file(file: UploadFile, prefix="image") -> str:
    """Save an uploaded file and return the path"""
    filename = generate_unique_filename(prefix)
    file_path = UPLOAD_DIR / filename
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    return str(file_path)

def process_images(person_image_path: str, garment_image_path: str) -> Tuple[Optional[str], str]:
    """Process images with the virtual try-on service"""
    try:
        logger.info(f"Processing images: {person_image_path} and {garment_image_path}")
        
        # Load person image
        logger.info("Loading person image")
        person_img = cv2.imread(person_image_path)
        if person_img is None:
            logger.error("Failed to load person image")
            return None, "We couldn't process your photo. Please ensure it's clearly visible and try again."
        person_img = cv2.cvtColor(person_img, cv2.COLOR_BGR2RGB)
        logger.info(f"Person image loaded successfully. Shape: {person_img.shape}")
        
        # Load garment image
        logger.info("Loading garment image")
        garment_img = cv2.imread(garment_image_path)
        if garment_img is None:
            logger.error("Failed to load garment image")
            return None, "We couldn't process the garment image. Please ensure it has a clear view of the clothing and try again."
        garment_img = cv2.cvtColor(garment_img, cv2.COLOR_BGR2RGB)
        logger.info(f"Garment image loaded successfully. Shape: {garment_img.shape}")
        
        # Initialize client
        logger.info("Initializing Kling AI client")
        client = KlingAIClient()
        
        # Process images
        logger.info("Calling Kling AI Virtual Try-on service")
        result_img, status_message = client.try_on(person_img, garment_img, random.randint(0, MAX_SEED))
        
        if result_img is None:
            logger.error(f"Kling AI processing failed. Status: {status_message}")
            return None, status_message
            
        # Save result
        result_filename = generate_unique_filename("result")
        result_path = STATIC_DIR / result_filename
        cv2.imwrite(str(result_path), cv2.cvtColor(result_img, cv2.COLOR_RGB2BGR))
        
        # Return the URL path to the result
        return f"/static/{result_filename}", "Success"
        
    except Exception as e:
        logger.error(f"Error processing images: {str(e)}")
        return None, f"Sorry, something went wrong while generating your try-on: {str(e)}"

def process_try_on_task(session_id: str, person_path: str, garment_path: str):
    """Background task to process try-on and store results"""
    try:
        result_url, status = process_images(person_path, garment_path)
        
        if result_url:
            user_results[session_id] = {
                'result_url': result_url,
                'status': 'completed',
                'message': 'Success'
            }
        else:
            user_results[session_id] = {
                'status': 'failed',
                'message': status
            }
    except Exception as e:
        logger.error(f"Error in background task: {str(e)}")
        user_results[session_id] = {
            'status': 'failed',
            'message': str(e)
        }

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Virtual Try-On API",
        "version": "1.0.0",
        "endpoints": {
            "POST /upload/person": "Upload person image",
            "POST /upload/garment": "Upload garment image",
            "POST /try-on": "Process try-on with uploaded images",
            "GET /result/{session_id}": "Get try-on result"
        }
    }

@app.post("/upload/person")
async def upload_person_image(
    file: UploadFile = File(...),
    session_id: str = Form(None)
):
    """
    Upload a person image for virtual try-on
    
    - **file**: The person image file
    - **session_id**: Optional session ID. If not provided, a new one will be generated
    
    Returns:
        session_id: The session ID for subsequent requests
        file_path: The path where the image was saved
    """
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # Generate session ID if not provided
    if not session_id:
        session_id = str(uuid.uuid4())
    
    try:
        # Save the uploaded file
        file_path = save_uploaded_file(file, "person")
        
        # Store the file path in the user_images dictionary
        if session_id not in user_images:
            user_images[session_id] = {}
        
        user_images[session_id]['person'] = file_path
        
        return {
            "session_id": session_id,
            "file_path": file_path,
            "message": "Person image uploaded successfully"
        }
    except Exception as e:
        logger.error(f"Error uploading person image: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error uploading image: {str(e)}")

@app.post("/upload/garment")
async def upload_garment_image(
    file: UploadFile = File(...),
    session_id: str = Form(...)
):
    """
    Upload a garment image for virtual try-on
    
    - **file**: The garment image file
    - **session_id**: Session ID from previous person image upload
    
    Returns:
        session_id: The session ID for subsequent requests
        file_path: The path where the image was saved
    """
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # Check if session exists
    if session_id not in user_images:
        raise HTTPException(status_code=404, detail="Session not found. Please upload a person image first.")
    
    try:
        # Save the uploaded file
        file_path = save_uploaded_file(file, "garment")
        
        # Store the file path in the user_images dictionary
        user_images[session_id]['garment'] = file_path
        
        return {
            "session_id": session_id,
            "file_path": file_path,
            "message": "Garment image uploaded successfully"
        }
    except Exception as e:
        logger.error(f"Error uploading garment image: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error uploading image: {str(e)}")

@app.post("/try-on")
async def try_on(
    background_tasks: BackgroundTasks,
    session_id: str = Form(...)
):
    """
    Process virtual try-on with previously uploaded images
    
    - **session_id**: Session ID from previous image uploads
    
    Returns:
        session_id: The session ID for retrieving results
        status: The status of the try-on process
    """
    # Check if session exists and has both images
    if session_id not in user_images:
        raise HTTPException(status_code=404, detail="Session not found. Please upload images first.")
    
    if 'person' not in user_images[session_id] or 'garment' not in user_images[session_id]:
        raise HTTPException(status_code=400, detail="Both person and garment images are required. Please upload missing images.")
    
    # Get image paths
    person_path = user_images[session_id]['person']
    garment_path = user_images[session_id]['garment']
    
    # Initialize result status
    user_results[session_id] = {
        'status': 'processing',
        'message': 'Processing your try-on request...'
    }
    
    # Process images in background
    background_tasks.add_task(process_try_on_task, session_id, person_path, garment_path)
    
    return {
        "session_id": session_id,
        "status": "processing",
        "message": "Try-on process started. Check result endpoint for status."
    }

@app.get("/result/{session_id}")
async def get_result(session_id: str):
    """
    Get the result of a virtual try-on process
    
    - **session_id**: Session ID from previous try-on request
    
    Returns:
        status: The status of the try-on process
        result_url: The URL of the result image (if completed)
    """
    # Check if session exists
    if session_id not in user_results:
        raise HTTPException(status_code=404, detail="Result not found. Please start a try-on process first.")
    
    result = user_results[session_id]
    
    if result['status'] == 'completed':
        # Get the server URL from the request
        base_url = "http://localhost:8000"  # Default for local testing
        
        # Construct the full URL for the result image
        full_result_url = f"{base_url}{result['result_url']}"
        
        return {
            "session_id": session_id,
            "status": "completed",
            "result_url": full_result_url,
            "message": "Try-on completed successfully"
        }
    elif result['status'] == 'failed':
        return {
            "session_id": session_id,
            "status": "failed",
            "message": result['message']
        }
    else:
        return {
            "session_id": session_id,
            "status": "processing",
            "message": "Try-on is still processing. Please check again later."
        }

@app.get("/image/{image_type}/{session_id}")
async def get_image(image_type: str, session_id: str):
    """
    Get the uploaded image for a session
    
    - **image_type**: Type of image (person or garment)
    - **session_id**: Session ID
    
    Returns:
        The image file
    """
    if image_type not in ['person', 'garment']:
        raise HTTPException(status_code=400, detail="Invalid image type. Must be 'person' or 'garment'.")
    
    if session_id not in user_images or image_type not in user_images[session_id]:
        raise HTTPException(status_code=404, detail=f"{image_type.capitalize()} image not found for this session.")
    
    image_path = user_images[session_id][image_type]
    return FileResponse(image_path)

# Cleanup function to remove old files
@app.on_event("startup")
async def startup_event():
    """Cleanup old files on startup"""
    try:
        # Remove files older than 24 hours
        current_time = time.time()
        for directory in [UPLOAD_DIR, STATIC_DIR]:
            for file_path in directory.glob("*"):
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > 86400:  # 24 hours in seconds
                        file_path.unlink()
        logger.info("Cleaned up old files")
    except Exception as e:
        logger.error(f"Error during startup cleanup: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8082, reload=True)
