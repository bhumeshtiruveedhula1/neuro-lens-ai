/**
 * NeuroLens AI — Response Transformer
 *
 * Converts the backend PredictResponse shape into the frontend
 * Metrics interface consumed by every UI component.
 *
 * This is the single bridging layer between backend and frontend
 * data contracts. No component code needs to understand the
 * backend response format.
 */

import type {
  CogState,
  ConnectionStatus,
  ContextualAction,
  Metrics,
  ReasonGroup,
} from '../hooks/useMetrics'

/* ── Backend response shape (read-only reference) ── */

export interface PredictResponse {
  fatigue_score: number
  state: string
  confidence: string
  reasons: {
    behavior: string[]
    session: string[]
    fatigue: string[]
  }
  trend: string
  trendDelta: number
  burnoutScore: number
  distractionLevel: number
  baselines: {
    typing_speed: number
    error_rate: number
    switching: number
  }
  anomalies: string[]
  actions: string[]
  last_updated: string
  status: string
}

/* ── Individual field mappers ── */

function mapState(backend: string): CogState {
  switch (backend) {
    case 'normal':
      return 'normal'
    case 'high_load':
      return 'moderate'
    case 'fatigue':
    case 'risk':
      return 'high'
    default:
      return 'normal'
  }
}

function mapConfidence(backend: string): number {
  switch (backend) {
    case 'low':
      return 30
    case 'medium':
      return 65
    case 'high':
      return 85
    default:
      return 50
  }
}

function mapTrend(backend: string): Metrics['trend'] {
  switch (backend) {
    case 'up':
      return 'rising'
    case 'down':
      return 'falling'
    case 'stable':
      return 'stable'
    default:
      return 'stable'
  }
}

function mapDistraction(value: number): Metrics['distractionLevel'] {
  if (value < 34) return 'low'
  if (value < 67) return 'moderate'
  return 'high'
}

function mapStatus(backend: string): ConnectionStatus {
  switch (backend) {
    case 'calibrating':
      return 'calibrating'
    case 'live':
      return 'live'
    case 'stale':
      return 'disconnected'
    default:
      return 'live'
  }
}

/* ── Structural transformers ── */

/**
 * Infer severity from the text content of a reason string.
 * Words that imply degradation → 'warn'; otherwise → 'info'.
 */
function inferSeverity(text: string): 'warn' | 'info' | 'neutral' {
  const lower = text.toLowerCase()
  const warnKeywords = [
    'elevated',
    'slower',
    'higher',
    'dropped',
    'drained',
    'tired',
    'risk',
    'long',
    'overdue',
    'erratic',
    'spiked',
    'rose',
    'below',
    'above',
  ]
  if (warnKeywords.some((kw) => lower.includes(kw))) return 'warn'
  return 'info'
}

/**
 * Backend reasons: `{ behavior: string[], session: string[], fatigue: string[] }`
 * Frontend expects: `ReasonGroup[]` with category/label/signals.
 */
function mapReasons(
  reasons: PredictResponse['reasons'] | undefined,
): ReasonGroup[] {
  const r = reasons ?? { behavior: [], session: [], fatigue: [] }
  const groups: ReasonGroup[] = []

  if (r.behavior?.length) {
    groups.push({
      category: 'behavior',
      label: 'Behavior signals',
      signals: r.behavior.map((text) => ({
        text,
        severity: inferSeverity(text),
      })),
    })
  }

  // Backend "session" → frontend "time" category
  if (r.session?.length) {
    groups.push({
      category: 'time',
      label: 'Session & time',
      signals: r.session.map((text) => ({
        text,
        severity: inferSeverity(text),
      })),
    })
  }

  if (r.fatigue?.length) {
    groups.push({
      category: 'fatigue',
      label: 'Fatigue trend',
      signals: r.fatigue.map((text) => ({
        text,
        severity: inferSeverity(text),
      })),
    })
  }

  return groups
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '')
}

/**
 * Backend actions: `string[]` → frontend: `ContextualAction[]`
 * First action is primary, second secondary, rest ghost.
 * Trigger is inferred from label keywords.
 */
function mapActions(actions: string[] | undefined): ContextualAction[] {
  const list = actions ?? []
  return list.map((text, i) => {
    const lower = text.toLowerCase()
    let trigger: ContextualAction['trigger'] = 'break'
    if (lower.includes('focus')) trigger = 'focus'
    else if (lower.includes('insight') || lower.includes('pattern'))
      trigger = 'insights'
    else if (lower.includes('dismiss') || lower.includes('ignore'))
      trigger = 'dismiss'

    return {
      id: slugify(text),
      label: text,
      description: '',
      type: (i === 0 ? 'primary' : i === 1 ? 'secondary' : 'ghost') as ContextualAction['type'],
      trigger,
    }
  })
}

/**
 * Convert ISO 8601 timestamp → seconds since that moment.
 */
function secondsAgo(iso: string | undefined): number {
  if (!iso) return 0
  try {
    return Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000))
  } catch {
    return 0
  }
}

/* ── Main transformer ── */

/**
 * Transforms a raw backend PredictResponse into the frontend Metrics
 * interface that every component already consumes.
 *
 * `prev` is the previous Metrics snapshot, used to carry forward
 * fields that the backend doesn't provide (sessionMin, scrollVelocity, etc.).
 */
export function transformPredictResponse(
  raw: Record<string, unknown>,
  prev?: Metrics,
): Metrics {
  // Cast for field access — all accesses are individually guarded
  const r = raw as unknown as PredictResponse

  const score = Math.round(r.fatigue_score ?? 0)
  const state = mapState(r.state)
  const confidence = mapConfidence(r.confidence)
  const trend = mapTrend(r.trend)
  const burnoutScore = r.burnoutScore ?? 0

  // Derive typing metrics from baselines (backend stores CPM, not WPM)
  const typingSpeedCpm = r.baselines?.typing_speed ?? 220
  const wpm = Math.round(typingSpeedCpm / 5) // CPM ÷ 5 ≈ WPM
  const wpmBaseline = prev?.wpmBaseline ?? Math.round(typingSpeedCpm / 5)

  // Backend stores ratio (0–1), frontend displays percentage
  const errorRate =
    Math.round((r.baselines?.error_rate ?? 0.03) * 1000) / 10

  // Backend stores per-minute, dashboard displays per-hour
  const switchingPerMin = r.baselines?.switching ?? 0.8
  const tabSwitches = Math.round(switchingPerMin * 60)
  const tabSwitchBaseline =
    prev?.tabSwitchBaseline ?? Math.round(switchingPerMin * 60)

  // Status-derived calibration fields
  const isCalibrating = r.status === 'calibrating'

  return {
    score,
    wpm,
    wpmBaseline,
    errorRate,
    focusDuration: prev?.focusDuration ?? 0,
    tabSwitches,
    tabSwitchBaseline,
    scrollVelocity: prev?.scrollVelocity ?? 'Normal',
    state,
    sessionMin: prev?.sessionMin ?? 0,
    confidence,
    trend,
    trendDelta: r.trendDelta ?? 0,
    burnoutScore,
    distractionLevel: mapDistraction(r.distractionLevel ?? 0),
    lastUpdatedSec: secondsAgo(r.last_updated),
    reasonGroups: mapReasons(r.reasons),
    actions: mapActions(r.actions),
    connectionStatus: mapStatus(r.status),
    calDaysTotal: isCalibrating ? 3 : 14,
    calProgress: isCalibrating ? 40 : 100,
  }
}
