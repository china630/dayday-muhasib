from fastapi import APIRouter

api_router = APIRouter()


@api_router.get("/status")
async def status():
    """API v1 status endpoint"""
    return {"status": "ok", "version": "v1"}
