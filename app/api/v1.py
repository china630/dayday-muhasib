from fastapi import APIRouter

from app.api.v1.wallet import router as wallet_router
from app.api.v1.tasks import router as tasks_router


api_router = APIRouter()

# Include sub-routers
api_router.include_router(wallet_router)
api_router.include_router(tasks_router)


@api_router.get("/status")
async def status():
    """API v1 status endpoint"""
    return {"status": "ok", "version": "v1"}
