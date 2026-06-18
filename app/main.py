"""
main.py — FastAPI application entrypoint for the delivery classification bot.

Wires CORS, the health probe, and the delivery router (classification +
delivery-status timeline). Backend/tracking integration and auth are still to
be layered in.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import delivery

app = FastAPI(
    title="Enterprise Book Store — Delivery Classification Bot",
    description="Classifies orders and decides dispatch time; maintains the delivery-status timeline.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
def health():
    """Liveness probe used by Render's health check."""
    return {"status": "ok"}


app.include_router(delivery.router, prefix="/delivery", tags=["Delivery"])
