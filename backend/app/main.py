from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.core.logging import setup_logging, get_logger
from app.db.session import create_tables, check_connection
from app.api.routes import health, chat, query, feedback

setup_logging(debug=settings.DEBUG)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Starting Clinical AI Assistant",
        extra={"version": settings.APP_VERSION, "environment": settings.ENVIRONMENT},
    )
    check_connection()
    create_tables()
    yield
    logger.info("Shutting down Clinical AI Assistant")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.API_PREFIX, tags=["health"])
app.include_router(chat.router, prefix=settings.API_PREFIX, tags=["chat"])
app.include_router(query.router, prefix=settings.API_PREFIX, tags=["query"])
app.include_router(feedback.router, prefix=settings.API_PREFIX, tags=["feedback"])
