#!/bin/bash

# Install dependencies
pip install -r requirements.txt

# Run the FastAPI server
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
