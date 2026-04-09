export function PrivacyPane() {
  const tracked = [
    { label: 'Typing rhythm (timing gaps only)', allowed: true },
    { label: 'Error correction count', allowed: true },
    { label: 'Tab switch frequency', allowed: true },
    { label: 'Scroll velocity', allowed: true },
    { label: 'What you type or paste', allowed: false },
    { label: 'Screenshots or screen content', allowed: false },
    { label: 'Location or persistent device ID', allowed: false },
  ]

  return (
    <div className="pane" style={{ maxWidth: 600 }}>
      {/* Shield banner */}
      <div style={{
        background: 'rgba(29,158,117,0.06)',
        border: '1px solid rgba(29,158,117,0.2)',
        borderRadius: 'var(--radius-lg)',
        padding: '16px 20px',
        marginBottom: '20px',
        display: 'flex',
        gap: '14px',
        alignItems: 'flex-start',
      }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1D9E75" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, marginTop: 2 }}>
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        </svg>
        <div>
          <div style={{ fontSize: '13px', fontWeight: 400, color: '#1D9E75', marginBottom: '4px', letterSpacing: '0.02em' }}>
            All processing runs locally on your device
          </div>
          <div style={{ fontSize: '11px', color: 'rgba(29,158,117,0.6)', fontWeight: 300, lineHeight: 1.6 }}>
            Nothing is transmitted to any server unless you explicitly enable sync.
          </div>
        </div>
      </div>

      {/* What we track */}
      <div className="surf" style={{ marginBottom: '16px' }}>
        <p className="label">What we track</p>
        {tracked.map((item, i) => (
          <div className="mrow" key={i}>
            <span className="key">{item.label}</span>
            <span className={item.allowed ? 'priv-yes' : 'priv-no'}>
              {item.allowed ? 'YES' : 'NEVER'}
            </span>
          </div>
        ))}
      </div>

      {/* Pipeline */}
      <div className="card">
        <p className="label">Processing pipeline</p>
        <div className="pipeline">
          <div className="pipeline-step">Behavior signals</div>
          <span className="pipeline-arrow">→</span>
          <div className="pipeline-step">Local ML model</div>
          <span className="pipeline-arrow">→</span>
          <div className="pipeline-step">Cognitive score</div>
          <span className="pipeline-arrow">→</span>
          <div className="pipeline-step" style={{ background: 'rgba(91,141,184,0.08)', borderColor: 'rgba(91,141,184,0.2)', color: '#5B8DB8' }}>
            Your insight
          </div>
        </div>
        <p style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '14px', fontWeight: 300, lineHeight: 1.7 }}>
          Intermediate signals are discarded after computing each score. No raw data persists.
        </p>
      </div>
    </div>
  )
}
