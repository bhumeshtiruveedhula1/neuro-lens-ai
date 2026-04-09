import { useState, useEffect } from 'react'
import { useCursor } from './hooks/useCursor'
import { useMetrics } from './hooks/useMetrics'
import { DashboardPane } from './components/DashboardPane'
import { AssessmentPane } from './components/AssessmentPane'
import { InsightsPane } from './components/InsightsPane'
import { PrivacyPane } from './components/PrivacyPane'
import { FocusPane } from './components/FocusPane'
import { AlertModal } from './components/AlertModal'
import { SystemStatusBar } from './components/SystemStatusBar'

type Tab = 'dash' | 'onboard' | 'insights' | 'privacy' | 'focus'

const TABS: { id: Tab; label: string }[] = [
  { id: 'dash', label: 'Dashboard' },
  { id: 'onboard', label: 'Assessment' },
  { id: 'insights', label: 'Insights' },
  { id: 'privacy', label: 'Privacy' },
  { id: 'focus', label: 'Focus Mode' },
]

export default function App() {
  const { dotRef, ringRef } = useCursor()
  const { metrics, history } = useMetrics()
  const [tab, setTab] = useState<Tab>('dash')
  const [showAlert, setShowAlert] = useState(false)

  // Re-attach cursor hover listeners on tab change
  useEffect(() => {
    const ring = ringRef.current
    if (!ring) return
    const onIn = () => ring.classList.add('hovered')
    const onOut = () => ring.classList.remove('hovered')
    const els = document.querySelectorAll('button, a, input, [data-cursor]')
    els.forEach(el => {
      el.addEventListener('mouseenter', onIn)
      el.addEventListener('mouseleave', onOut)
    })
    return () => {
      els.forEach(el => {
        el.removeEventListener('mouseenter', onIn)
        el.removeEventListener('mouseleave', onOut)
      })
    }
  }, [tab, metrics])

  const stateColor = metrics.state === 'high' ? '#C8893A' : metrics.state === 'moderate' ? '#5B8DB8' : '#1D9E75'

  return (
    <>
      <div ref={dotRef} className="cursor-dot" />
      <div ref={ringRef} className="cursor-ring" />
      <div className="scanline" />

      <div className="app-shell">
        {/* ── Header ── */}
        <header className="header">
          <div className="logo-mark">
            <div className="logo-icon">N</div>
            <div className="logo-text">
              <div className="logo-name">NeuroLens AI</div>
              <div className="logo-sub">Cognitive monitor</div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 300, color: 'var(--text-tertiary)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
              Load&nbsp;
              <span style={{ color: stateColor, fontWeight: 400, transition: 'color 0.5s' }}>
                {metrics.score}
              </span>
            </div>
            <div className="status-pill">
              <span className="status-dot" />
              <span className="status-text">Local only · No keylogging</span>
            </div>
          </div>
        </header>

        {/* ── System Status Bar ── */}
        <SystemStatusBar metrics={metrics} />

        {/* ── Nav Tabs ── */}
        <nav className="nav-tabs">
          {TABS.map(t => (
            <button
              key={t.id}
              className={`nav-tab ${tab === t.id ? 'active' : ''}`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </nav>

        {/* ── Main ── */}
        <main className="main-content">
          {tab === 'dash' && (
            <DashboardPane
              metrics={metrics}
              history={history}
              onShowAlert={() => setShowAlert(true)}
              onGoInsights={() => setTab('insights')}
              onGoFocus={() => setTab('focus')}
            />
          )}
          {tab === 'onboard' && (
            <AssessmentPane onComplete={() => setTab('dash')} />
          )}
          {tab === 'insights' && <InsightsPane metrics={metrics} />}
          {tab === 'privacy' && <PrivacyPane />}
          {tab === 'focus' && (
            <FocusPane metrics={metrics} onExit={() => setTab('dash')} />
          )}
        </main>

        <footer className="footer-line">
          <span className="footer-tag">NeuroLens AI — v2.0.0</span>
          <span className="footer-tag">
            {metrics.calDaysTotal} days calibrated · All data processed locally
          </span>
        </footer>
      </div>

      {showAlert && (
        <AlertModal
          metrics={metrics}
          onClose={() => setShowAlert(false)}
          onFocusMode={() => setTab('focus')}
          onGoInsights={() => setTab('insights')}
        />
      )}
    </>
  )
}
