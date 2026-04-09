import { useState } from 'react'

interface Props {
  onComplete: () => void
}

const STEPS = [
  {
    q: 'How long can you focus before feeling distracted?',
    hint: 'This helps us calibrate your baseline attention span.',
    options: ['Under 25 min', '25 – 45 min', '45 – 90 min', '90 min +'],
    type: 'grid' as const,
  },
  {
    q: 'Current stress level',
    hint: 'Slide to reflect how you feel right now.',
    options: [],
    type: 'slider' as const,
  },
  {
    q: 'How do you prefer to work?',
    hint: 'We adapt alerts to your natural rhythm.',
    options: ['Deep work — long uninterrupted blocks', 'Sprint + rest — Pomodoro-style cycles', 'Reactive — respond as tasks arrive'],
    type: 'list' as const,
  },
]

export function AssessmentPane({ onComplete }: Props) {
  const [step, setStep] = useState(0)
  const [selected, setSelected] = useState<Record<number, string>>({})
  const [slider, setSlider] = useState(5)
  const [done, setDone] = useState(false)

  const current = STEPS[step]
  const pct = ((step + 1) / (STEPS.length + 1)) * 100

  function handleNext() {
    if (step < STEPS.length - 1) {
      setStep(s => s + 1)
    } else {
      setDone(true)
    }
  }

  if (done) {
    return (
      <div className="pane" style={{ maxWidth: 520, margin: '0 auto', textAlign: 'center', padding: '40px 0' }}>
        <div className="check-ring">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#1D9E75" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        </div>
        <p className="section-heading">Baseline captured</p>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', margin: '10px 0 32px', fontWeight: 300, lineHeight: 1.7 }}>
          NeuroLens will now calibrate to your personal rhythm over the next 7 days.
        </p>
        <button className="btn btn-accent" style={{ padding: '10px 32px' }} onClick={onComplete}>
          Open Dashboard
        </button>
      </div>
    )
  }

  return (
    <div className="pane" style={{ maxWidth: 520, margin: '0 auto' }}>
      {/* Progress */}
      <div style={{ marginBottom: '32px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
          <span className="step-label">Step {step + 1} of {STEPS.length}</span>
          <span className="step-label">{Math.round(pct)}%</span>
        </div>
        <div className="progress-bar">
          <div className="progress-fill" style={{ width: pct + '%' }} />
        </div>
      </div>

      <div className="card" style={{ marginBottom: '16px' }}>
        <p className="step-question">{current.q}</p>
        <p className="step-hint">{current.hint}</p>

        {current.type === 'grid' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
            {current.options.map(opt => (
              <button
                key={opt}
                className={`option-btn ${selected[step] === opt ? 'selected' : ''}`}
                onClick={() => setSelected(s => ({ ...s, [step]: opt }))}
              >
                {opt}
              </button>
            ))}
          </div>
        )}

        {current.type === 'list' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0' }}>
            {current.options.map(opt => (
              <button
                key={opt}
                className={`option-btn ${selected[step] === opt ? 'selected' : ''}`}
                onClick={() => setSelected(s => ({ ...s, [step]: opt }))}
              >
                {opt}
              </button>
            ))}
          </div>
        )}

        {current.type === 'slider' && (
          <div>
            <input
              type="range"
              min={0}
              max={10}
              value={slider}
              onChange={e => setSlider(+e.target.value)}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-tertiary)', letterSpacing: '0.08em' }}>
              <span>Calm</span>
              <span style={{ color: 'var(--text-secondary)' }}>{slider}</span>
              <span>Overwhelmed</span>
            </div>
          </div>
        )}
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
        {step > 0 && (
          <button className="btn btn-ghost" onClick={() => setStep(s => s - 1)}>Back</button>
        )}
        <button className="btn btn-accent" onClick={handleNext}>
          {step < STEPS.length - 1 ? 'Continue' : 'Complete'}
        </button>
      </div>
    </div>
  )
}
