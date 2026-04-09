import type { Metrics } from '../hooks/useMetrics'

interface Props {
  metrics: Metrics
  onClose: () => void
  onFocusMode: () => void
  onGoInsights: () => void
}

function getAlertConfig(metrics: Metrics) {
  const { state, burnoutScore, sessionMin, trend, score } = metrics

  if (burnoutScore > 75 || (state === 'high' && sessionMin > 80)) {
    return {
      iconColor: '#C0504A',
      iconBg: 'rgba(192,80,74,0.1)',
      iconBorder: 'rgba(192,80,74,0.2)',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#C0504A" strokeWidth="1.5" strokeLinecap="round">
          <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
      ),
      headline: 'Your brain needs a break',
      body: `You've used ${Math.round(burnoutScore)}% of your daily cognitive budget. Pushing further typically leads to more errors, not more output.`,
      primary: { label: 'Take a 15-min break', trigger: 'close' },
      secondary: { label: 'Start a focus timer', trigger: 'focus' },
      ghost: null,
    }
  }

  if (state === 'high' && trend === 'rising') {
    return {
      iconColor: '#C8893A',
      iconBg: 'rgba(200,137,58,0.1)',
      iconBorder: 'rgba(200,137,58,0.2)',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#C8893A" strokeWidth="1.5" strokeLinecap="round">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      ),
      headline: 'Load is rising — act early',
      body: `Your score is ${score} and climbing. Catching this now is easier than recovering after it peaks. A 10-min reset often brings load back to normal.`,
      primary: { label: 'Take a 10-min break', trigger: 'close' },
      secondary: { label: 'Enter Focus Mode', trigger: 'focus' },
      ghost: { label: 'See my patterns', trigger: 'insights' },
    }
  }

  if (state === 'high') {
    return {
      iconColor: '#C8893A',
      iconBg: 'rgba(200,137,58,0.1)',
      iconBorder: 'rgba(200,137,58,0.2)',
      icon: (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#C8893A" strokeWidth="1.5" strokeLinecap="round">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      ),
      headline: 'High cognitive load detected',
      body: `You've been at ${score} for an extended period. Your error rate is elevated. A short break will help more than pushing through.`,
      primary: { label: 'Take a break', trigger: 'close' },
      secondary: { label: 'Focus Mode', trigger: 'focus' },
      ghost: { label: 'Ignore for now', trigger: 'close' },
    }
  }

  // moderate / default
  return {
    iconColor: '#5B8DB8',
    iconBg: 'rgba(91,141,184,0.1)',
    iconBorder: 'rgba(91,141,184,0.2)',
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#5B8DB8" strokeWidth="1.5" strokeLinecap="round">
        <circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" />
      </svg>
    ),
    headline: 'Heads up — load is moderate',
    body: 'Nothing urgent, but you\'re on an upward trend. A focused work session now could help you stay in a productive zone.',
    primary: { label: 'Enter Focus Mode', trigger: 'focus' },
    secondary: { label: 'View insights', trigger: 'insights' },
    ghost: { label: 'Dismiss', trigger: 'close' },
  }
}

export function AlertModal({ metrics, onClose, onFocusMode, onGoInsights }: Props) {
  const cfg = getAlertConfig(metrics)

  const handle = (trigger: string) => {
    if (trigger === 'focus') { onFocusMode(); onClose() }
    else if (trigger === 'insights') { onGoInsights(); onClose() }
    else onClose()
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={e => e.stopPropagation()}>
        <div
          className="modal-icon"
          style={{ background: cfg.iconBg, border: `1px solid ${cfg.iconBorder}` }}
        >
          {cfg.icon}
        </div>

        <p className="modal-title">{cfg.headline}</p>
        <p className="modal-body">{cfg.body}</p>

        {/* Score strip */}
        <div className="modal-score-strip">
          <span className="modal-score-key">Current load</span>
          <div className="modal-score-bar">
            <div
              className="modal-score-fill"
              style={{
                width: metrics.score + '%',
                background: cfg.iconColor,
              }}
            />
          </div>
          <span className="modal-score-num" style={{ color: cfg.iconColor }}>{metrics.score}</span>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 24 }}>
          <button
            className="btn btn-accent"
            style={{ width: '100%', justifyContent: 'center', padding: '11px 20px', borderColor: cfg.iconColor + '50', background: cfg.iconBg, color: cfg.iconColor }}
            onClick={() => handle(cfg.primary.trigger)}
          >
            {cfg.primary.label}
          </button>
          {cfg.secondary && (
            <button className="btn" style={{ width: '100%', justifyContent: 'center' }} onClick={() => handle(cfg.secondary!.trigger)}>
              {cfg.secondary.label}
            </button>
          )}
          {cfg.ghost && (
            <button className="btn btn-ghost" style={{ width: '100%', justifyContent: 'center' }} onClick={() => handle(cfg.ghost!.trigger)}>
              {cfg.ghost.label}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
