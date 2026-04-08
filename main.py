from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from metrics import router as metrics_router
from ml.inference import router as ml_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="NeuroLens AI",
    version="2.0.0",
    description="Privacy-first cognitive fatigue monitoring backend with rolling features, local ML inference, and real-time state streaming.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "chrome-extension://*", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(metrics_router, tags=["metrics"])
app.include_router(ml_router, prefix="/ml", tags=["ml"])


@app.get("/")
async def root():
    return {
        "service": "NeuroLens AI",
        "version": "2.0.0",
        "docs": "/docs",
        "key_endpoints": {
            "POST /profile/onboarding": "Save per-user onboarding and preferences",
            "POST /metrics": "Send one-minute aggregated telemetry; backend computes 5-minute features and predictions",
            "GET /state/latest": "Latest personalized cognitive state",
            "GET /metrics/history": "Recent state history for charts",
            "GET /burnout/trend": "Daily burnout trend summary",
            "GET /notifications": "Recent nudges and interventions",
            "WS /ws/live": "Live stream of predictions",
        },
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "NeuroLens AI", "version": "2.0.0"}
