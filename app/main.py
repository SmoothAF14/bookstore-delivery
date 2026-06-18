"""
main.py — FastAPI application entrypoint for the delivery classification bot.

Minimal bootable app: exposes `app` (the ASGI application) and a working
/health endpoint so the container deploys cleanly. Delivery routers and the
classification/dispatch wiring are still placeholders to be implemented.
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Enterprise Book Store — Delivery Classification Bot",
    description="Classifies orders and decides dispatch time; maintains the delivery-status timeline.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — comma-separated origins from env (default: allow all for now).
_cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
def health():
    """Liveness probe used by Render's health check."""
    return {"status": "ok"}


# TODO: Wire routers — health (move here), delivery.
# TODO: Load settings from app.core.config once implemented.
