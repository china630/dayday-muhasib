from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.core.config import settings
from app.db.session import init_db, close_db
from app.api.v1 import api_router


# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.DEBUG else logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    """
    logger.info("Starting up DayDay Tax API...")
    await init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down DayDay Tax API...")
    await close_db()
    logger.info("Database connections closed")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
    description="""
    DayDay Tax API - Tax Automation for Azerbaijan
    
    ## Features
    
    * **Wallet Management**: Check balance, deposit via MilliÖN terminals
    * **Task Management**: Create and track automated tax tasks (filing, debt checks, inbox scans)
    * **Message Retrieval**: Access tax authority inbox messages with risk flagging
    * **Automated Billing**: Monthly subscription billing (10 AZN/month)
    
    ## Authentication
    
    For MVP: Use Bearer token format `voen:{YOUR_VOEN}`
    
    Example: `Authorization: Bearer voen:1234567890`
    """,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/")
async def root():
    """Root endpoint - API health check"""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {"status": "healthy"}


@app.get("/health/db")
async def database_health():
    """Database health check"""
    try:
        from app.db.session import engine
        from sqlalchemy import text
        
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}


@app.get("/health/celery")
async def celery_health():
    """Celery worker health check"""
    try:
        from app.worker import celery_app
        
        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        
        if stats:
            return {
                "status": "healthy",
                "workers": len(stats),
                "worker_list": list(stats.keys())
            }
        else:
            return {
                "status": "unhealthy",
                "workers": 0,
                "message": "No workers detected"
            }
    except Exception as e:
        logger.error(f"Celery health check failed: {e}")
        return {"status": "unhealthy", "workers": 0, "error": str(e)}
