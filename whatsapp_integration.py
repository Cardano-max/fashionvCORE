import os
import uuid
import time
import json
import logging
import requests
import cv2
import numpy as np
from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import tempfile
import shutil
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Wylto API Configuration
WYLTO_API_TOKEN = os.getenv("WYLTO_API_TOKEN")
WYLTO_API_BASE = "https://server.wylto.com/api/v1"

# Application directories
UPLOAD_DIR = "uploads"
RESULTS_DIR = "results"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# Initialize FastAPI app
app = FastAPI(title="WhatsApp Virtual Try-On Integration")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static directories
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/results", StaticFiles(directory=RESULTS_DIR), name="results")

# User session storage
user_sessions = {}

# Classes for request/response models
class WebhookPayload(BaseModel):
    contactId: str
    clientContactId: Optional[str] = None
    conversationId: Optional[str] = None
    clientMessageId: Optional[str] = None
    message: Dict[str, Any]

# Helper functions
def generate_unique_filename(prefix="file", suffix=".jpg"):
    """Generate a unique filename"""
    timestamp = int(time.time())
    unique_id = str(uuid.uuid4())[:8]
    return f"{prefix}_{timestamp}_{unique_id}{suffix}"

def download_image_from_url(url):
    """Download an image from a URL"""
    try:
        logger.info(f"Downloading image from URL: {url}")
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            # Create a temporary file
            filename = generate_unique_filename()
            filepath = os.path.join(UPLOAD_DIR, filename)
            
            # Save the image
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"Image downloaded and saved to {filepath}")
            return filepath
        else:
            logger.error(f"Failed to download image. Status code: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Error downloading image: {str(e)}")
        return None

def send_whatsapp_message(contact_id, message_data):
    """Send a WhatsApp message via Wylto API"""
    try:
        url = f"{WYLTO_API_BASE}/wa/send/{contact_id}"
        headers = {
            "Authorization": f"Bearer {WYLTO_API_TOKEN}",
            "Content-Type": "application/json"
        }
        
        logger.info(f"Sending message to {contact_id}: {json.dumps(message_data)}")
        
        response = requests.post(url, headers=headers, json={"message": message_data}, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"Failed to send message: Status {response.status_code}, {response.text}")
            return False
            
        logger.info(f"Message sent successfully: {response.text}")
        return True
    except Exception as e:
        logger.error(f"Error sending WhatsApp message: {str(e)}")
        return False

def process_virtual_tryon(person_image_path, garment_image_path):
    """Process virtual try-on using the original app.py functionality"""
    from app import process_images  # Import from your original Flask app
    
    try:
        logger.info(f"Processing virtual try-on with person: {person_image_path}, garment: {garment_image_path}")
        result = process_images(person_image_path, garment_image_path)
        
        if result["status"] == "success":
            # Get the result path and convert to URL
            result_path = result["result_path"]
            result_filename = os.path.basename(result_path)
            
            # For simplicity, we'll copy the result file to our results directory
            shutil.copyfile(result_path, os.path.join(RESULTS_DIR, result_filename))
            
            # Build a public URL
            server_url = os.getenv("SERVER_URL", "https://your-server.com")
            result_url = f"{server_url}/results/{result_filename}"
            
            logger.info(f"Try-on successful, result URL: {result_url}")
            return {"status": "success", "result_url": result_url}
        else:
            logger.error(f"Try-on failed: {result['message']}")
            return {"status": "error", "message": result["message"]}
    except Exception as e:
        logger.error(f"Error in virtual try-on: {str(e)}")
        return {"status": "error", "message": f"Processing error: {str(e)}"}

# API Endpoints
@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "WhatsApp Virtual Try-On Integration"}

@app.post("/webhook")
async def webhook(payload: WebhookPayload, background_tasks: BackgroundTasks):
    """Webhook endpoint for receiving WhatsApp messages"""
    try:
        logger.info(f"Received webhook payload: {json.dumps(payload.dict())}")
        
        contact_id = payload.contactId
        message = payload.message
        message_type = message.get("type")
        
        # Process different message types
        if message_type == "text":
            # Handle text messages
            text_content = message.get("text", {}).get("body", "").lower()
            
            # Handle different commands
            if text_content in ["hi", "hello", "start", "try on"]:
                # Send welcome message
                send_whatsapp_message(contact_id, {
                    "type": "text",
                    "text": {
                        "body": "👋 Welcome to the Virtual Try-On service! Send me a photo of a person (full body, front facing) to start."
                    }
                })
                # Initialize session
                user_sessions[contact_id] = {
                    "state": "awaiting_person",
                    "timestamp": time.time()
                }
            elif text_content == "help":
                send_whatsapp_message(contact_id, {
                    "type": "text",
                    "text": {
                        "body": "📱 *Virtual Try-On Help*\n\n"
                              "1. Send 'start' to begin\n"
                              "2. Send a full-body photo of a person\n"
                              "3. Send a photo of a garment\n"
                              "4. Wait for your virtual try-on result!\n\n"
                              "Type 'reset' to start over at any time."
                    }
                })
            elif text_content == "reset":
                # Reset the session
                if contact_id in user_sessions:
                    del user_sessions[contact_id]
                send_whatsapp_message(contact_id, {
                    "type": "text",
                    "text": {
                        "body": "Session reset. Send 'start' to begin again."
                    }
                })
            else:
                # Default response if no session exists
                if contact_id not in user_sessions:
                    send_whatsapp_message(contact_id, {
                        "type": "text",
                        "text": {
                            "body": "Send 'start' to begin using the Virtual Try-On service."
                        }
                    })
                elif user_sessions[contact_id]["state"] == "awaiting_person":
                    send_whatsapp_message(contact_id, {
                        "type": "text",
                        "text": {
                            "body": "Please send a photo of a person to continue."
                        }
                    })
                elif user_sessions[contact_id]["state"] == "awaiting_garment":
                    send_whatsapp_message(contact_id, {
                        "type": "text",
                        "text": {
                            "body": "Please send a photo of a garment to continue."
                        }
                    })
                    
        elif message_type == "image":
            # Handle image messages
            image_data = message.get("image", {})
            image_url = image_data.get("url")
            
            if not image_url:
                logger.error("No image URL in the message")
                send_whatsapp_message(contact_id, {
                    "type": "text",
                    "text": {
                        "body": "Sorry, I couldn't find the image. Please try again."
                    }
                })
                return {"status": "error", "message": "No image URL"}
            
            # Download the image
            image_path = download_image_from_url(image_url)
            
            if not image_path:
                send_whatsapp_message(contact_id, {
                    "type": "text",
                    "text": {
                        "body": "Sorry, I couldn't download the image. Please try again."
                    }
                })
                return {"status": "error", "message": "Failed to download image"}
            
            # Process based on session state
            if contact_id not in user_sessions:
                # No active session, assume this is a person image
                user_sessions[contact_id] = {
                    "state": "awaiting_garment",
                    "person_image": image_path,
                    "timestamp": time.time()
                }
                send_whatsapp_message(contact_id, {
                    "type": "text",
                    "text": {
                        "body": "Great! Now send me a photo of the garment you want to try on."
                    }
                })
            elif user_sessions[contact_id]["state"] == "awaiting_person":
                # Update session with person image
                user_sessions[contact_id]["person_image"] = image_path
                user_sessions[contact_id]["state"] = "awaiting_garment"
                send_whatsapp_message(contact_id, {
                    "type": "text",
                    "text": {
                        "body": "Great! Now send me a photo of the garment you want to try on."
                    }
                })
            elif user_sessions[contact_id]["state"] == "awaiting_garment":
                # Process the garment image
                person_image = user_sessions[contact_id]["person_image"]
                garment_image = image_path
                
                # Notify user
                send_whatsapp_message(contact_id, {
                    "type": "text",
                    "text": {
                        "body": "Processing your virtual try-on... This may take a few moments."
                    }
                })
                
                # Process the try-on in a background task
                background_tasks.add_task(
                    process_and_send_result,
                    contact_id,
                    person_image,
                    garment_image
                )
                
                # Reset session
                del user_sessions[contact_id]
        
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return {"status": "error", "message": str(e)}

async def process_and_send_result(contact_id, person_image, garment_image):
    """Process try-on and send result back to the user"""
    try:
        # Process the try-on
        result = process_virtual_tryon(person_image, garment_image)
        
        if result["status"] == "success":
            # Send the result image
            send_whatsapp_message(contact_id, {
                "type": "image",
                "image": {
                    "url": result["result_url"],
                    "caption": "Here's your virtual try-on result! ✨"
                }
            })
            
            # Send follow-up message
            send_whatsapp_message(contact_id, {
                "type": "text",
                "text": {
                    "body": "Want to try another outfit? Just send me another person photo to start again."
                }
            })
        else:
            # Send error message
            send_whatsapp_message(contact_id, {
                "type": "text",
                "text": {
                    "body": f"Sorry, there was an error processing your images: {result['message']}. Please try again."
                }
            })
    except Exception as e:
        logger.error(f"Error in process_and_send_result: {str(e)}")
        send_whatsapp_message(contact_id, {
            "type": "text",
            "text": {
                "body": "Sorry, something went wrong while processing your images. Please try again."
            }
        })
    finally:
        # Clean up temporary files
        try:
            if os.path.exists(person_image):
                os.remove(person_image)
            if os.path.exists(garment_image):
                os.remove(garment_image)
        except Exception as e:
            logger.error(f"Error cleaning up files: {str(e)}")

# Run the application
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("whatsapp_integration:app", host="0.0.0.0", port=8000, reload=True)