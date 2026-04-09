import type { Metrics } from '../hooks/useMetrics'

interface Props {
  metrics: Metrics
}

function freshnessLabel(secs: number): string {
  if (secs < 4) return 'Just now'
  if (secs < 10) return `${secs}s ago`
  if (secs < 60) return `${secs}s ago`
  return `${Math.floor(secs / 60)}m ago`
}

function freshnessColor(secs: number): string {
  if (secs < 8) return 'var(--green)'
  if (secs < 20) return '#C8893A'
  return '#C0504A'
}

const CONNECTION_CONFIG = {
  live: { dot: 'var(--green)', label: 'Live', pulse: true },
  updating: { dot: '#5B8DB8', label: 'Updating', pulse: true },
  calibrating: { dot: '#C8893A', label: 'Calibrating', pulse: true },
  disconnected: { dot: 'rgba(255,255,255,0.2)', label: 'Disconnected', pulse: false },
}

export function SystemStatusBar({ metrics }: Props) {
  const { connectionStatus, confidence, lastUpdatedSec, calProgress, calDaysTotal, burnoutScore, trend, trendDelta } = metrics
  const conn = CONNECTION_CONFIG[connectionStatus]

  const trendIcon = trend === 'rising' ? '↑' : trend === 'falling' ? '↓' : '→'
  const trendColor = trend === 'rising' ? '#C8893A' : trend === 'falling' ? '#1D9E75' : 'var(--text-tertiary)'

  return (
    <div className="system-status-bar">
      {/* Connection */}
      <div className="ssb-item">
        <span
          className={`ssb-dot ${conn.pulse ? 'ssb-dot-pulse' : ''}`}
          style={{ background: conn.dot }}
        />
        <span className="ssb-label">{conn.label}</span>
      </div>

      <span className="ssb-sep" />

      {/* Confidence */}
      <div className="ssb-item" title={`Model confidence based on ${calDaysTotal} days of data`}>
        <span className="ssb-meta-key">Confidence</span>
        <div className="ssb-conf-bar">
          <div
            className="ssb-conf-fill"
            style={{
              width: confidence + '%',
              background: confidence > 75 ? 'var(--green)' : confidence > 50 ? '#C8893A' : '#C0504A',
            }}
          />
        </div>
        <span className="ssb-meta-val">{Math.round(confidence)}%</span>
      </div>

      <span className="ssb-sep" />

      {/* Trend */}
      <div className="ssb-item">
        <span className="ssb-meta-key">Trend</span>
        <span className="ssb-meta-val" style={{ color: trendColor }}>
          {trendIcon} {Math.abs(trendDelta) < 1 ? 'Stable' : `${Math.abs(trendDelta) > 5 ? 'Fast ' : ''}${trend}`}
        </span>
      </div>

      <span className="ssb-sep" />

      {/* Burnout bar */}
      <div className="ssb-item" title="Cumulative cognitive load today">
        <span className="ssb-meta-key">Daily budget</span>
        <div className="ssb-conf-bar" style={{ width: 60 }}>
          <div
            className="ssb-conf-fill"
            style={{
              width: burnoutScore + '%',
              background: burnoutScore > 70 ? '#C0504A' : burnoutScore > 45 ? '#C8893A' : 'var(--green)',
            }}
          />
        </div>
        <span className="ssb-meta-val">{Math.round(burnoutScore)}%</span>
      </div>

      <span className="ssb-sep" />

      {/* Freshness */}
      <div className="ssb-item">
        <span className="ssb-meta-key">Updated</span>
        <span
          className="ssb-meta-val"
          style={{ color: freshnessColor(lastUpdatedSec) }}
        >
          {freshnessLabel(lastUpdatedSec)}
        </span>
      </div>

      {/* Cal info — only if not fully calibrated */}
      {calProgress < 100 && (
        <>
          <span className="ssb-sep" />
          <div className="ssb-item">
            <span className="ssb-meta-key">Calibration</span>
            <div className="ssb-conf-bar" style={{ width: 50 }}>
              <div className="ssb-conf-fill" style={{ width: calProgress + '%', background: '#5B8DB8' }} />
            </div>
            <span className="ssb-meta-val">{Math.round(calProgress)}%</span>
          </div>
        </>
      )}
    </div>
  )
}
