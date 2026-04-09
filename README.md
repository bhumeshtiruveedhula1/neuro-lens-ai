# NeuroLens AI

Privacy-first cognitive fatigue and load companion built for students, developers, and knowledge workers.

## What Was Reused

- Existing FastAPI backend and real-time ingestion routes.
- Existing rolling 5-minute feature engine and dual-score inference flow (`fatigue_score`, `load_score`).
- Existing onboarding/profile, self-report, calibration, notifications, and chat pipeline.
- Existing extension telemetry stream and chat bridge.

## What Was Added

- New backend endpoints for hackathon demo modules:
  - `POST /video-sessions`
  - `GET /video-sessions`
  - `GET /video-sessions/summary`
  - `GET /telemetry/recent`
- New backend storage table: `video_sessions`.
- Extended onboarding profile fields for break habit, short-video effect, and productivity goal.
- New multi-view premium frontend experience:
  - Dashboard
  - Typing Lab
  - Video Tracker / Escape Behavior
  - Alerts & Interventions
  - App Breakdown
  - Onboarding + EMA Calibration
  - Confidence / Explainability panel
- Manual short-form video logging with metadata-only escape behavior proxy.
- Privacy/trust messaging across the app.

## Future Work

- Add automated short-form detection from extension active-tab metadata (no content inspection).
- Introduce optional probability calibration and richer confidence decomposition.
- Add SHAP-backed explanations in the UI when full feature attribution is enabled.
- Add user-level Model A training pipeline execution on uploaded labeled data.

## Run Locally

### Backend

```bash
uvicorn main:app --reload --port 8001
```

### Frontend

```bash
cd neurolens-ui
npm run dev
```

### Tests

```bash
python -m unittest discover -s tests -v
```

## Privacy Guardrails

- No raw key text capture
- No screenshot capture
- No message/content scraping
- Metadata only: timing, counts, durations, app/domain context
