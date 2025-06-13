import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="Log File Server",
    description="Server to serve static files from logs directory",
)

# Get the logs directory path
logs_dir = Path(__file__).parent / "logs"

# Mount the logs directory as static files
app.mount("/logs", StaticFiles(directory=str(logs_dir)), name="logs")


@app.get("/")
async def root():
    """Root endpoint that provides information about available log files"""
    try:
        log_files = [
            f for f in os.listdir(logs_dir) if os.path.isfile(os.path.join(logs_dir, f))
        ]
        return {
            "message": "Log File Server",
            "description": "Access log files at /logs/{filename}",
            "available_files": log_files,
            "example": "/logs/scraper.log",
        }
    except Exception as e:
        return {"message": "Log File Server", "error": str(e)}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
