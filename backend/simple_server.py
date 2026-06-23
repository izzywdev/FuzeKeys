from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="FuzeKeys API Test")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "FuzeKeys API is running", "status": "healthy"}

@app.get("/health")
async def health():
    return {"status": "healthy", "database": "connected (SQLite)"}

if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8000) 