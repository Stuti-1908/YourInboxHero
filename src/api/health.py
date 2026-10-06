from fastapi import APIRouter
import time

router = APIRouter()
START_TIME = time.time()


@router.get('/healthz')
def health_check():
    """Health check endpoint for Azure App Service slot swap verification."""
    uptime = time.time() - START_TIME
    return {"status": "ok", "uptime": uptime}
