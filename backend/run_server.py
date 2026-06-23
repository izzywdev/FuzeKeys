#!/usr/bin/env python3
"""
Simple script to run the FastAPI server
"""
import uvicorn
from app.main import app

if __name__ == "__main__":
    print("Starting FuzeKeys API server...")
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="info"
    ) 