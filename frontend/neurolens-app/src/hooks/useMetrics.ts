import { useState, useEffect, useRef } from 'react'
import { fetchPrediction, generateSimulatedTelemetry } from '../services/api'
import { transformPredictResponse } from '../services/transform'

export type CogState = 'normal' | 'moderate' | 'high'
export type ConnectionStatus = 'calibrating' | 'live' | 'updating' | 'disconnected'

export interface ReasonGroup {
  category: 'behavior' | 'time' | 'fatigue'
  label: string
  signals: { text: string; severity: 'warn' | 'info' | 'neutral' }[]
}

export interface ContextualAction {
  id: string
  label: string
  description: string
  type: 'primary' | 'secondary' | 'ghost'
  trigger: 'focus' | 'break' | 'dismiss' | 'insights'
}

export interface Metrics {
  score: number
  wpm: number
  wpmBaseline: number
  errorRate: number
  focusDuration: number
  tabSwitches: number
  tabSwitchBaseline: number
  scrollVelocity: 'Slow' | 'Normal' | 'Fast' | 'Erratic'
  state: CogState
  sessionMin: number
  confidence: number
  trend: 'rising' | 'stable' | 'falling'
  trendDelta: number
  burnoutScore: number
  distractionLevel: 'low' | 'moderate' | 'high'
  lastUpdatedSec: number
  reasonGroups: ReasonGroup[]
  actions: ContextualAction[]
  connectionStatus: ConnectionStatus
  calDaysTotal: number
  calProgress: number
}

function getState(score: number): CogState {
  if (score < 40) return 'normal'
  if (score < 65) return 'moderate'
  return 'high'
}

function computeReasonGroups(
  wpm: number, wpmBaseline: number,
  errorRate: number,
  tabSwitches: number, tabSwitchBaseline: number,
  sessionMin: number,
  burnoutScore: number,
  score: number
): ReasonGroup[] {
  const groups: ReasonGroup[] = []

  const behaviorSignals: ReasonGroup['signals'] = []
  const wpmDiff = Math.round(((wpmBaseline - wpm) / wpmBaseline) * 100)
  if (wpmDiff > 10)
    behaviorSignals.push({ text: `Typing ${wpmDiff}% slower than your ${wpmBaseline} WPM baseline`, severity: 'warn' })
  else if (wpmDiff < -8)
    behaviorSignals.push({ text: `Typing ${Math.abs(wpmDiff)}% faster — sustained focus burst`, severity: 'info' })

  if (errorRate > 3.5)
    behaviorSignals.push({ text: `Error corrections ${((errorRate / 2.1 - 1) * 100).toFixed(0)}% above your normal rate`, severity: 'warn' })

  const tabDiff = tabSwitches - tabSwitchBaseline
  if (tabDiff > 3)
    behaviorSignals.push({ text: `Tab switching at ${tabSwitches}/hr — ${tabDiff} above your baseline`, severity: 'warn' })
  else if (tabDiff < -2)
    behaviorSignals.push({ text: 'Low tab switching — staying in one place', severity: 'info' })

  if (behaviorSignals.length > 0)
    groups.push({ category: 'behavior', label: 'Behavior signals', signals: behaviorSignals })

  const timeSignals: ReasonGroup['signals'] = []
  if (sessionMin > 90)
    timeSignals.push({ text: `${sessionMin} min continuous — past your 2.8hr saturation point`, severity: 'warn' })
  else if (sessionMin > 45)
    timeSignals.push({ text: `${sessionMin} min in — approaching your focus fatigue window`, severity: 'info' })

  const hour = new Date().getHours()
  if (hour >= 14 && hour <= 16)
    timeSignals.push({ text: 'Post-lunch window — your historically lowest focus period', severity: 'neutral' })
  else if (hour >= 9 && hour <= 11)
    timeSignals.push({ text: 'Morning peak window — your data shows strongest recall now', severity: 'info' })
  else if (hour >= 20)
    timeSignals.push({ text: 'Late session — fatigue compounds after 8PM', severity: 'neutral' })

  if (timeSignals.length > 0)
    groups.push({ category: 'time', label: 'Session & time', signals: timeSignals })

  const fatigueSignals: ReasonGroup['signals'] = []
  if (burnoutScore > 70)
    fatigueSignals.push({ text: `Burnout risk elevated — ${Math.round(burnoutScore)}% of daily cognitive budget used`, severity: 'warn' })
  else if (burnoutScore > 45)
    fatigueSignals.push({ text: `${Math.round(burnoutScore)}% of daily cognitive load used — moderate accumulation`, severity: 'info' })

  if (score > 65 && sessionMin > 30)
    fatigueSignals.push({ text: 'High load sustained — recovery window overdue', severity: 'warn' })

  if (fatigueSignals.length > 0)
    groups.push({ category: 'fatigue', label: 'Fatigue trend', signals: fatigueSignals })

  return groups
}

function computeActions(state: CogState, sessionMin: number, burnoutScore: number, trend: string): ContextualAction[] {
  if (state === 'high' || burnoutScore > 65) {
    return [
      { id: 'break', label: 'Take a 10-min break', description: 'Step away and reset. You\'ve earned it.', type: 'primary', trigger: 'break' },
      { id: 'focus', label: 'Enter Focus Mode', description: 'Contain the session with a timer.', type: 'secondary', trigger: 'focus' },
      { id: 'insights', label: 'Review your patterns', description: 'Understand when this typically happens.', type: 'ghost', trigger: 'insights' },
    ]
  }
  if (state === 'moderate') {
    if (trend === 'rising') {
      return [
        { id: 'focus', label: 'Enter Focus Mode now', description: 'Catch it before load peaks further.', type: 'primary', trigger: 'focus' },
        { id: 'break', label: 'Quick 5-min pause', description: 'A micro-break resets momentum.', type: 'secondary', trigger: 'break' },
      ]
    }
    return [
      { id: 'focus', label: 'Lock in with Focus Mode', description: 'Stable window — good time to go deep.', type: 'primary', trigger: 'focus' },
      { id: 'insights', label: 'View today\'s patterns', description: 'Understand your rhythm.', type: 'ghost', trigger: 'insights' },
    ]
  }
  return [
    { id: 'focus', label: 'Start a deep work session', description: 'Conditions are optimal right now.', type: 'primary', trigger: 'focus' },
    { id: 'insights', label: 'Review weekly insights', description: '14 days of patterns available.', type: 'ghost', trigger: 'insights' },
  ]
}

const INITIAL_HISTORY = [28, 31, 29, 35, 40, 44, 41, 47, 52, 55, 58, 60, 64, 62, 67, 70, 72, 74, 72]
const HISTORY_CAP = 50

/**
 * Demo fallback: applies the original random-walk mutation to prev metrics.
 * Used when the backend is unreachable so the UI stays alive.
 */
function applyDemoFallback(prev: Metrics, tick: number): Metrics {
  const delta = Math.round((Math.random() - 0.48) * 7)
  const score = Math.max(20, Math.min(95, prev.score + delta))
  const wpm = Math.round(38 + (Math.random() - 0.5) * 8)
  const errorRate = parseFloat((4.2 + (Math.random() - 0.5) * 1.2).toFixed(1))
  const tabSwitches = Math.round(12 + (Math.random() - 0.5) * 5)
  const sessionMin = tick % 4 === 0 ? prev.sessionMin + 1 : prev.sessionMin
  const burnoutScore = Math.min(100, prev.burnoutScore + (score > 65 ? 0.4 : score > 40 ? 0.15 : -0.1))
  const state = getState(score)
  const trendDelta = score - prev.score
  const trend: Metrics['trend'] = Math.abs(trendDelta) < 3 ? 'stable' : trendDelta > 0 ? 'rising' : 'falling'
  const confidence = Math.min(100, Math.max(55, prev.confidence + (Math.random() - 0.5) * 4))
  const velocities: Metrics['scrollVelocity'][] = ['Normal', 'Normal', 'Normal', 'Slow', 'Fast', 'Erratic']
  const scrollVelocity = velocities[Math.floor(Math.random() * velocities.length)]
  return {
    ...prev, score, wpm, errorRate, tabSwitches, sessionMin,
    focusDuration: sessionMin, burnoutScore, state, trendDelta, trend,
    confidence, scrollVelocity, lastUpdatedSec: 0,
    distractionLevel: tabSwitches > 14 ? 'high' : tabSwitches > 10 ? 'moderate' : 'low',
    reasonGroups: computeReasonGroups(wpm, prev.wpmBaseline, errorRate, tabSwitches, prev.tabSwitchBaseline, sessionMin, burnoutScore, score),
    actions: computeActions(state, sessionMin, burnoutScore, trend),
    connectionStatus: 'disconnected',
  }
}

export function useMetrics() {
  const tickRef = useRef(0)
  const lastSecRef = useRef(0)
  const fetchingRef = useRef(false) // prevent overlapping API calls

  const [metrics, setMetrics] = useState<Metrics>(() => {
    const score = 72, wpm = 38, wpmBaseline = 49
    const errorRate = 4.2, tabSwitches = 12, tabSwitchBaseline = 9
    const sessionMin = 47, burnoutScore = 58
    const state = getState(score)
    const trend: Metrics['trend'] = 'rising'
    return {
      score, wpm, wpmBaseline, errorRate,
      focusDuration: 47, tabSwitches, tabSwitchBaseline,
      scrollVelocity: 'Normal', state, sessionMin,
      confidence: 78, trend, trendDelta: 9,
      burnoutScore, distractionLevel: 'moderate',
      lastUpdatedSec: 0,
      reasonGroups: computeReasonGroups(wpm, wpmBaseline, errorRate, tabSwitches, tabSwitchBaseline, sessionMin, burnoutScore, score),
      actions: computeActions(state, sessionMin, burnoutScore, trend),
      connectionStatus: 'live', calDaysTotal: 14, calProgress: 100,
    }
  })

  const [history, setHistory] = useState<number[]>(INITIAL_HISTORY)

  /* ── 1-second freshness counter (unchanged) ── */
  useEffect(() => {
    const id = setInterval(() => {
      lastSecRef.current += 1
      setMetrics(m => ({ ...m, lastUpdatedSec: lastSecRef.current }))
    }, 1000)
    return () => clearInterval(id)
  }, [])

  /* ── 3-second main loop: fetch → transform → fallback ── */
  useEffect(() => {
    const interval = setInterval(async () => {
      tickRef.current++
      const tick = tickRef.current

      // Guard against overlapping requests
      if (fetchingRef.current) return
      fetchingRef.current = true

      try {
        // 1. Generate simulated telemetry to exercise the full backend ML pipeline
        const telemetry = generateSimulatedTelemetry()

        // 2. POST to /predict
        const response = await fetchPrediction(telemetry)

        // 3. Transform backend response → Metrics interface
        setMetrics(prev => {
          const transformed = transformPredictResponse(response, prev)

          // Preserve locally-tracked session timer
          const sessionMin = tick % 4 === 0 ? prev.sessionMin + 1 : prev.sessionMin

          // Smooth scroll velocity (backend doesn't track this)
          const velocities: Metrics['scrollVelocity'][] = ['Normal', 'Normal', 'Normal', 'Slow', 'Fast', 'Erratic']
          const scrollVelocity = velocities[Math.floor(Math.random() * velocities.length)]

          lastSecRef.current = 0
          return {
            ...transformed,
            sessionMin,
            focusDuration: sessionMin,
            scrollVelocity,
            lastUpdatedSec: 0,
          }
        })

        // 4. Update history with the new backend score (capped at HISTORY_CAP)
        const backendScore = Math.round(
          Number((response as Record<string, unknown>).fatigue_score) || 0
        )
        setHistory(prev => {
          const next = [...prev, Math.max(0, Math.min(100, backendScore))]
          return next.length > HISTORY_CAP ? next.slice(next.length - HISTORY_CAP) : next
        })

      } catch {
        // ── FALLBACK: keep UI alive with the original random walk ──
        setMetrics(prev => {
          lastSecRef.current = 0
          return applyDemoFallback(prev, tick)
        })
        setHistory(prev => {
          const next = [...prev, Math.max(20, Math.min(95, 72 + Math.round((Math.random() - 0.48) * 10)))]
          return next.length > HISTORY_CAP ? next.slice(next.length - HISTORY_CAP) : next
        })
      } finally {
        fetchingRef.current = false
      }
    }, 3000)

    return () => clearInterval(interval)
  }, [])

  return { metrics, history }
}

