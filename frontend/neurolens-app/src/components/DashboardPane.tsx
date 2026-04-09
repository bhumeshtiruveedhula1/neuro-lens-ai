import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import { GaugeCanvas } from './GaugeCanvas'
import type { Metrics } from '../hooks/useMetrics'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip)

interface Props {
  metrics: Metrics
  history: number[]
  onShowAlert: () => void
  onGoInsights: () => void
  onGoFocus: () => void
}

const CHART_LABELS = [
  '-90m', '', '', '-75m', '', '', '-60m', '',
  '', '-45m', '', '', '-30m', '', '', '-15m', '', '', 'Now'
]

export function getStateColor(state: Metrics['state']) {
  if (state === 'normal') return { bg: 'rgba(29,158,117,0.1)', text: '#1D9E75', label: 'Normal' }
  if (state === 'moderate') return { bg: 'rgba(91,141,184,0.1)', text: '#5B8DB8', label: 'Moderate' }
  return { bg: 'rgba(200,137,58,0.1)', text: '#C8893A', label: 'High Load' }
}

const CATEGORY_ICON: Record<string, string> = {
  behavior: '⌨',
  time: '◷',
  fatigue: '◉',
}

function BurnoutMini({ value }: { value: number }) {
  const color = value > 70 ? '#C0504A' : value > 45 ? '#C8893A' : '#1D9E75'
  const segments = 10
  const filled = Math.round((value / 100) * segments)
  return (
    <div style={{ display: 'flex', gap: 3, alignItems: 'center' }}>
      {Array.from({ length: segments }).map((_, i) => (
        <div
          key={i}
          style={{
            width: 8, height: 3,
            borderRadius: 1,
            background: i < filled ? color : 'rgba(255,255,255,0.07)',
            transition: 'background 0.4s',
          }}
        />
      ))}
    </div>
  )
}

export function DashboardPane({ metrics, history, onShowAlert, onGoInsights, onGoFocus }: Props) {
  const stateInfo = getStateColor(metrics.state)

  const handleAction = (trigger: string) => {
    if (trigger === 'focus') onGoFocus()
    else if (trigger === 'insights') onGoInsights()
    else if (trigger === 'break') onShowAlert()
  }

  const chartData = {
    labels: CHART_LABELS,
    datasets: [{
      data: history,
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.45,
      fill: true,
      backgroundColor: (ctx: any) => {
        const g = ctx.chart.ctx.createLinearGradient(0, 0, 0, 160)
        g.addColorStop(0, 'rgba(29,158,117,0.07)')
        g.addColorStop(1, 'rgba(29,158,117,0)')
        return g
      },
      segment: {
        borderColor: (ctx: any) => {
          const v = ctx.p1.parsed.y
          return v < 40 ? '#1D9E75' : v < 65 ? '#C8893A' : '#C0504A'
        },
      },
      borderColor: '#C8893A',
    }]
  }

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 600 },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#0f0f0d',
        borderColor: 'rgba(255,255,255,0.08)',
        borderWidth: 1,
        titleColor: 'rgba(232,228,220,0.35)',
        bodyColor: '#e8e4dc',
        titleFont: { family: '"DM Mono"', size: 10, weight: '300' as const },
        bodyFont: { family: '"DM Mono"', size: 11 },
        padding: 10,
        callbacks: { label: (ctx: any) => `load: ${Math.round(ctx.raw)}` }
      }
    },
    scales: {
      x: {
        grid: { color: 'rgba(255,255,255,0.03)' },
        ticks: { color: 'rgba(232,228,220,0.18)', font: { size: 9, family: '"DM Mono"' }, maxRotation: 0 },
        border: { color: 'rgba(255,255,255,0.05)' }
      },
      y: {
        min: 0, max: 100,
        grid: { color: 'rgba(255,255,255,0.03)' },
        ticks: { color: 'rgba(232,228,220,0.18)', font: { size: 9, family: '"DM Mono"' }, stepSize: 25 },
        border: { color: 'rgba(255,255,255,0.05)' }
      }
    }
  }

  const trendIcon = metrics.trend === 'rising' ? '↑' : metrics.trend === 'falling' ? '↓' : '→'
  const trendColor = metrics.trend === 'rising' ? '#C8893A' : metrics.trend === 'falling' ? '#1D9E75' : 'var(--text-tertiary)'

  return (
    <div className="pane">

      {/* ── Data Ticker ── */}
      <div className="data-ticker">
        <div className="ticker-inner">
          {[0, 1].map(i => (
            <div key={i} style={{ display: 'flex', gap: '60px' }}>
              <div className="ticker-item">WPM <span className="ticker-val">{metrics.wpm}</span></div>
              <div className="ticker-item">Baseline <span className="ticker-val">{metrics.wpmBaseline} WPM</span></div>
              <div className="ticker-item">Errors <span className="ticker-val">{metrics.errorRate}%</span></div>
              <div className="ticker-item">Tab switches <span className="ticker-val">{metrics.tabSwitches}/hr</span></div>
              <div className="ticker-item">Session <span className="ticker-val">{metrics.sessionMin} min</span></div>
              <div className="ticker-item">Cognitive <span className="ticker-val">{metrics.score}</span></div>
              <div className="ticker-item">Daily budget <span className="ticker-val">{Math.round(metrics.burnoutScore)}%</span></div>
              <div className="ticker-item">Confidence <span className="ticker-val">{Math.round(metrics.confidence)}%</span></div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Top 3-col grid ── */}
      <div className="grid-3">

        {/* ── Card 1: State ── */}
        <div className="card state-card" style={{ textAlign: 'center' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
            <p className="label" style={{ margin: 0 }}>Cognitive State</p>
            <span
              className="trend-chip"
              style={{ color: trendColor, borderColor: trendColor + '40', background: trendColor + '10' }}
            >
              {trendIcon} {metrics.trend}
            </span>
          </div>

          <GaugeCanvas score={metrics.score} />

          <div className="score-number" key={metrics.score} style={{ marginTop: 8 }}>
            {metrics.score}
          </div>
          <div className="state-badge" style={{ background: stateInfo.bg, color: stateInfo.text }}>
            {stateInfo.label}
          </div>

          {/* Confidence row */}
          <div className="conf-row">
            <span className="conf-label">Model confidence</span>
            <div className="conf-track">
              <div
                className="conf-fill"
                style={{
                  width: metrics.confidence + '%',
                  background: metrics.confidence > 75 ? 'var(--green)' : '#C8893A',
                }}
              />
            </div>
            <span className="conf-pct">{Math.round(metrics.confidence)}%</span>
          </div>

          <p style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 6, letterSpacing: '0.06em' }}>
            Session: {metrics.sessionMin} min
          </p>
        </div>

        {/* ── Card 2: Why this state ── */}
        <div className="surf reasons-card">
          <p className="label">Why this state?</p>

          {metrics.reasonGroups.length === 0 ? (
            <p style={{ fontSize: 12, color: 'var(--text-tertiary)', fontWeight: 300 }}>
              Conditions look normal — no significant signals detected.
            </p>
          ) : (
            <div className="reason-groups">
              {metrics.reasonGroups.map((group, gi) => (
                <div key={group.category} className="reason-group" style={{ animationDelay: `${gi * 0.06}s` }}>
                  <div className="reason-group-header">
                    <span className="reason-group-icon">{CATEGORY_ICON[group.category]}</span>
                    <span className="reason-group-label">{group.label}</span>
                  </div>
                  {group.signals.map((sig, si) => (
                    <div
                      key={si}
                      className="reason-item"
                      style={{ animationDelay: `${gi * 0.06 + si * 0.04}s` }}
                    >
                      <span
                        className="reason-dot"
                        style={{
                          background:
                            sig.severity === 'warn' ? '#C8893A' :
                            sig.severity === 'info' ? '#5B8DB8' :
                            'var(--text-tertiary)'
                        }}
                      />
                      <span className="reason-text">{sig.text}</span>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}

          {/* Distraction indicator */}
          <div className="distraction-row">
            <span className="distraction-label">Distraction level</span>
            <span
              className="distraction-badge"
              style={{
                color: metrics.distractionLevel === 'high' ? '#C0504A' : metrics.distractionLevel === 'moderate' ? '#C8893A' : '#1D9E75',
                background: metrics.distractionLevel === 'high' ? 'rgba(192,80,74,0.08)' : metrics.distractionLevel === 'moderate' ? 'rgba(200,137,58,0.08)' : 'rgba(29,158,117,0.08)',
              }}
            >
              {metrics.distractionLevel}
            </span>
          </div>
        </div>

        {/* ── Card 3: Actions + Metrics ── */}
        <div className="surf actions-card">
          {/* Contextual Actions */}
          <p className="label">Recommended actions</p>
          <div className="actions-list">
            {metrics.actions.map((action, i) => (
              <button
                key={action.id}
                className={`action-btn action-btn-${action.type}`}
                onClick={() => handleAction(action.trigger)}
                style={{ animationDelay: `${i * 0.07}s` }}
              >
                <span className="action-btn-label">{action.label}</span>
                <span className="action-btn-desc">{action.description}</span>
              </button>
            ))}
          </div>

          {/* Burnout mini */}
          <div className="divider" style={{ margin: '16px 0 14px' }} />
          <p className="label" style={{ marginBottom: 8 }}>Daily cognitive budget</p>
          <BurnoutMini value={metrics.burnoutScore} />
          <p style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 6, fontWeight: 300, letterSpacing: '0.04em' }}>
            {Math.round(metrics.burnoutScore)}% of estimated daily capacity used
          </p>
        </div>
      </div>

      {/* ── Live Metrics row ── */}
      <div className="live-metrics-bar card" style={{ marginBottom: 20 }}>
        <p className="label" style={{ marginBottom: 12 }}>Live signals</p>
        <div className="live-metrics-grid">
          {[
            { key: 'Typing speed', val: `${metrics.wpm} WPM`, baseline: `baseline ${metrics.wpmBaseline}`, flagged: metrics.wpm < metrics.wpmBaseline * 0.85 },
            { key: 'Error rate', val: `${metrics.errorRate}%`, baseline: 'baseline 2.1%', flagged: metrics.errorRate > 3.5 },
            { key: 'Focus duration', val: `${metrics.focusDuration} min`, baseline: '', flagged: false },
            { key: 'Tab switches/hr', val: String(metrics.tabSwitches), baseline: `baseline ${metrics.tabSwitchBaseline}`, flagged: metrics.tabSwitches > metrics.tabSwitchBaseline + 3 },
            { key: 'Scroll velocity', val: metrics.scrollVelocity, baseline: '', flagged: metrics.scrollVelocity === 'Erratic' },
          ].map(item => (
            <div key={item.key} className="live-metric-cell">
              <span className="live-metric-key">{item.key}</span>
              <span className="live-metric-val" style={{ color: item.flagged ? '#C8893A' : 'var(--text-primary)' }}>
                {item.val}
                {item.flagged && <span className="live-metric-flag">△</span>}
              </span>
              {item.baseline && (
                <span className="live-metric-base">{item.baseline}</span>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ── Time Chart ── */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div>
            <p className="label" style={{ margin: 0 }}>Cognitive Load · Last 90 min</p>
          </div>
          <div style={{ display: 'flex', gap: 16, fontSize: 10, color: 'var(--text-tertiary)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
            {[['#1D9E75', 'Normal'], ['#C8893A', 'High'], ['#C0504A', 'Risk']].map(([c, l]) => (
              <span key={l} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <span style={{ width: 14, height: 1, background: c, display: 'inline-block' }} />{l}
              </span>
            ))}
          </div>
        </div>
        <div style={{ position: 'relative', height: 160 }}>
          <Line data={chartData} options={chartOptions} />
        </div>
      </div>

      {/* ── Footer row ── */}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button className="btn btn-ghost" onClick={onGoInsights}>See Insights</button>
        <button className="btn btn-accent" onClick={onGoFocus}>Enter Focus Mode</button>
      </div>
    </div>
  )
}
