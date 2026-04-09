from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.predict import router as predict_router
from backend.core.database import init_db
from backend.core.metrics import router as metrics_router

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

app.include_router(predict_router, tags=["predict"])
app.include_router(metrics_router, tags=["metrics"])


@app.get("/")
async def root():
    return {
        "service": "NeuroLens AI",
        "version": "2.0.0",
        "docs": "/docs",
        "key_endpoints": {
            "POST /predict": "Frontend-facing intelligence snapshot with trend, baselines, anomalies, actions, and demo fallback",
            "POST /profile/onboarding": "Save per-user onboarding and preferences",
            "POST /metrics": "Send one-minute aggregated telemetry; backend computes 5-minute features and predictions",
            "GET /state/latest": "Latest personalized cognitive state",
            "GET /metrics/history": "Recent state history for charts",
            "GET /burnout/trend": "Daily burnout trend summary",
            "GET /notifications": "Recent nudges and interventions",
            "POST /video-sessions": "Log short-form video metadata sessions",
            "GET /video-sessions/summary": "Daily escape-behavior proxy summary",
            "GET /telemetry/recent": "Recent app/domain metadata rows for dashboard breakdown",
            "POST /eye/metrics": "Ingest eye-fatigue metrics (EAR, blink, closure)",
            "GET /eye/latest": "Latest eye fatigue/drowsiness state",
            "GET /app-breakdown": "Classified productive vs entertainment app usage impact",
            "WS /ws/live": "Live stream of predictions",
        },
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "NeuroLens AI", "version": "2.0.0"}
