import { useState, useEffect, useRef } from 'react'
import type { Metrics } from '../hooks/useMetrics'

interface Props {
  metrics: Metrics
  onExit: () => void
}

function getStateColor(state: Metrics['state']) {
  if (state === 'normal') return '#1D9E75'
  if (state === 'moderate') return '#5B8DB8'
  return '#C8893A'
}

function getStateLabel(state: Metrics['state']) {
  if (state === 'normal') return 'Normal'
  if (state === 'moderate') return 'Moderate'
  return 'High Load'
}

export function FocusPane({ metrics, onExit }: Props) {
  const [secs, setSecs] = useState(25 * 60)
  const [running, setRunning] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (running) {
      intervalRef.current = setInterval(() => {
        setSecs(s => Math.max(0, s - 1))
      }, 1000)
    } else {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [running])

  const mm = String(Math.floor(secs / 60)).padStart(2, '0')
  const ss = String(secs % 60).padStart(2, '0')
  const progress = (secs / (25 * 60)) * 100
  const stateColor = getStateColor(metrics.state)
  const stateLabel = getStateLabel(metrics.state)

  return (
    <div className="pane" style={{ textAlign: 'center', padding: '32px 0' }}>
      {/* Breathing ring with SVG progress */}
      <div style={{ position: 'relative', width: 200, height: 200, margin: '0 auto 32px' }}>
        {/* Outer glow ring */}
        <svg
          style={{ position: 'absolute', inset: 0, animation: 'breathe 5s ease-in-out infinite' }}
          viewBox="0 0 200 200"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <circle cx="100" cy="100" r="96" stroke="rgba(255,255,255,0.04)" strokeWidth="1" />
          <circle cx="100" cy="100" r="88" stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
          {/* Progress arc */}
          <circle
            cx="100"
            cy="100"
            r="88"
            stroke={stateColor}
            strokeWidth="1"
            strokeOpacity="0.5"
            strokeDasharray={`${2 * Math.PI * 88}`}
            strokeDashoffset={`${2 * Math.PI * 88 * (1 - progress / 100)}`}
            strokeLinecap="round"
            transform="rotate(-90 100 100)"
            style={{ transition: 'stroke-dashoffset 1s linear' }}
          />
        </svg>

        {/* Center */}
        <div style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'var(--bg-3)',
          borderRadius: '50%',
          margin: '14px',
          border: '1px solid var(--border)',
        }}>
          <div className="focus-clock">{mm}:{ss}</div>
          <div className="focus-clock-sub">remaining</div>
        </div>
      </div>

      <div className="section-heading" style={{ marginBottom: '6px' }}>
        {running ? 'Focus session active' : secs === 0 ? 'Session complete' : 'Ready to focus'}
      </div>
      <p style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 300, letterSpacing: '0.04em', marginBottom: '20px' }}>
        Notifications paused · Alerts minimized
      </p>

      <div style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '8px',
        background: 'var(--bg-3)',
        border: '1px solid var(--border)',
        borderRadius: '20px',
        padding: '6px 16px',
        marginBottom: '28px',
      }}>
        <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>State</span>
        <span style={{ fontSize: '11px', fontWeight: 400, color: stateColor, letterSpacing: '0.04em' }}>
          {stateLabel} · {metrics.score}
        </span>
      </div>

      <div style={{ display: 'flex', justifyContent: 'center', gap: '8px' }}>
        <button
          className="btn btn-accent"
          onClick={() => setRunning(r => !r)}
        >
          {running ? 'Pause' : secs === 0 ? 'Restart' : 'Start'}
        </button>
        <button className="btn" onClick={onExit}>Exit Focus</button>
      </div>
    </div>
  )
}
