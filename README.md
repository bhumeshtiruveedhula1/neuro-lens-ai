<<<<<<< HEAD
# NeuroLens AI

Privacy-first cognitive-fatigue monitoring with:

- a local browser agent
- a FastAPI backend
- a rolling 5-minute feature pipeline
- a friendly dashboard with a floating companion chat

## What is now implemented

- Minute-level metadata ingestion (no content capture).
- Real-time fatigue/load predictions every minute.
- First-week onboarding + adaptive profile fields.
- Chat-based daily check-ins and break prompts.
- Self-report logging linked to surrounding model context.
- A "baby model" calibration layer that shifts per-user thresholds from strong labels.
- Live dashboard cards for state, reasons, trend, and a "Today" summary.

## Local run

### Backend

```bash
uvicorn main:app --reload --port 8001
```

### Frontend

```bash
cd neurolens-ui
npm run dev
```

### Extension

Load `chrome_extension/` as an unpacked extension in Chrome.
It sends minute telemetry to:

`http://localhost:8001/metrics?user_id=default`

## Main API routes

- `POST /profile/onboarding`
- `GET /profile/onboarding`
- `POST /metrics`
- `GET /state/latest`
- `GET /metrics/history`
- `GET /burnout/trend`
- `GET /notifications`
- `GET /chat/thread`
- `POST /chat/message`
- `POST /self-reports`
- `GET /calibration/status`
- `WS /ws/live`

## End-to-end flow

1. Content script collects only metadata (timing, counts, switches, idle, active domain/path).
2. Background worker aggregates to one-minute payloads and retries on backend downtime.
3. Backend builds a rolling 5-minute feature window and computes raw + z-scored features.
4. Main model predicts `p_high_load`, `p_fatigue`, `load_score`, `fatigue_score`.
5. Calibration layer updates user-specific thresholds from self-reports.
6. Companion layer sends supportive prompts and stores chat events.
7. Dashboard streams live state and chat updates through WebSocket.

## First-week personalization

- `model_maturity` increases from 0 to 1 based on windows + days.
- Companion limits question volume (roughly <= 4 short interactions/day).
- Profile features include:
  - `focus_capacity_minutes`
  - `break_style`
  - `user_target_hours`
  - `focus_apps` / `distraction_apps`
  - `baseline_fatigue_week` / `baseline_stress_week`

## Baby model calibration

The calibration layer is rules-based (hackathon-friendly):

1. Convert self-reports into strong labels:
   - fatigue/fogginess >= 8 -> `confirmed_high_fatigue`
   - fatigue/fogginess <= 2 -> `confirmed_safe`
   - severe support messages -> `severe_stress_event`
2. Save label + nearby main-model score.
3. Shift user cutoffs from defaults (`40/65/80`) to better match reported reality.
4. Keep the main ML model and calibration logic separate for easy future fine-tuning.

## Supportive companion behavior

- Break suggestion:
  - "You’ve been pushing hard for a while. Want to take a 3-minute pause?"
- Check-ins:
  - "On a scale from 0 to 10, how foggy does your mind feel right now?"
- Support mode for heavy messages:
  - "I’m really sorry you’re feeling this way. You are not alone."
- Positive reinforcement:
  - "Nice, you took a break before you were totally drained."

## Tests

```bash
python -m unittest discover -s tests -v
```

Current coverage includes:

- feature generation sanity
- model status endpoint
- ingestion -> prediction -> history pipeline

## Privacy guardrails

- No raw key text.
- No message content scraping.
- No screenshots.
- Only timestamps, counts, durations, and app/domain metadata are processed.
=======
# neuro-lens-ai
>>>>>>> 9ac0d1e98950bc0a580bf71f257c3333e7e3a567
