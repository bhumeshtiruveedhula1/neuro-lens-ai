import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
} from 'chart.js'
import { Bar, Line } from 'react-chartjs-2'
import type { Metrics } from '../hooks/useMetrics'

ChartJS.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, Filler, Tooltip)

const WK_DATA = [62, 71, 85, 68, 55, 30, 25]
const WK_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

// Focus decay curve: drops after ~2.5hrs
const DECAY_DATA = [88, 90, 91, 89, 86, 82, 77, 71, 64, 56, 49, 42, 35]
const DECAY_LABELS = ['0', '15', '30', '45', '60', '75', '90', '105', '120', '135', '150', '165', '180']

// Burnout trend over 14 days
const BURNOUT_TREND = [35, 42, 58, 71, 60, 55, 38, 45, 62, 78, 70, 65, 55, 58]
const BURNOUT_LABELS = Array.from({ length: 14 }, (_, i) => i === 0 ? '14d ago' : i === 13 ? 'Today' : '')

// Hour heatmap: avg load 6am–10pm
const HOUR_DATA = [28, 32, 45, 68, 82, 79, 71, 74, 88, 76, 62, 55, 48, 52, 66, 70, 64, 58, 50, 44, 36, 28, 22, 18]
const HOUR_LABELS = Array.from({ length: 24 }, (_, i) => i % 3 === 0 ? `${i}h` : '')

const BASE_CHART = {
  responsive: true as const,
  maintainAspectRatio: false as const,
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
    }
  },
}

const TICK_STYLE = { color: 'rgba(232,228,220,0.2)' as const, font: { size: 9, family: '"DM Mono"' as const } }
const GRID_STYLE = { color: 'rgba(255,255,255,0.03)' as const }
const BORDER_STYLE = { color: 'rgba(255,255,255,0.05)' as const }

const PATTERNS = [
  {
    icon: '◷',
    title: 'Focus drops after 2.8 hours',
    detail: 'Your attention degrades sharply around the 2.5hr mark. This pattern appears in 12 of 14 tracked sessions.',
    color: '#C8893A',
  },
  {
    icon: '☀',
    title: 'Peak window: 9–11 AM',
    detail: 'Your cognitive score averages 31% higher in this window. Best for deep, creative, or complex work.',
    color: '#1D9E75',
  },
  {
    icon: '⇌',
    title: 'High switching Tuesdays & Wednesdays',
    detail: 'Tab switching spikes mid-week. Correlates with highest weekly load scores (71 and 85).',
    color: '#5B8DB8',
  },
  {
    icon: '◉',
    title: 'Burnout accumulates Mon–Wed',
    detail: 'You consistently exhaust more cognitive budget early in the week, leading to lower Friday load.',
    color: '#C0504A',
  },
]

interface Props {
  metrics?: Metrics
}

export function InsightsPane({ metrics }: Props) {
  const barColors = WK_DATA.map(v => v < 40 ? '#1D9E75' : v < 65 ? '#C8893A' : '#C0504A')

  const weeklyChartData = {
    labels: WK_LABELS,
    datasets: [{
      data: WK_DATA,
      backgroundColor: barColors.map(c => c + '55'),
      borderColor: barColors,
      borderWidth: 1,
      borderRadius: 3,
      borderSkipped: false,
    }]
  }

  const decayData = {
    labels: DECAY_LABELS,
    datasets: [{
      data: DECAY_DATA,
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.4,
      fill: true,
      borderColor: '#5B8DB8',
      backgroundColor: (ctx: any) => {
        const g = ctx.chart.ctx.createLinearGradient(0, 0, 0, 120)
        g.addColorStop(0, 'rgba(91,141,184,0.1)')
        g.addColorStop(1, 'rgba(91,141,184,0)')
        return g
      },
    }]
  }

  const burnoutTrendData = {
    labels: BURNOUT_LABELS,
    datasets: [{
      data: BURNOUT_TREND,
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.4,
      fill: true,
      segment: {
        borderColor: (ctx: any) => {
          const v = ctx.p1.parsed.y
          return v > 70 ? '#C0504A' : v > 45 ? '#C8893A' : '#1D9E75'
        }
      },
      borderColor: '#C8893A',
      backgroundColor: (ctx: any) => {
        const g = ctx.chart.ctx.createLinearGradient(0, 0, 0, 100)
        g.addColorStop(0, 'rgba(200,137,58,0.08)')
        g.addColorStop(1, 'rgba(200,137,58,0)')
        return g
      },
    }]
  }

  const hourHeatmapData = {
    labels: HOUR_LABELS,
    datasets: [{
      data: HOUR_DATA,
      backgroundColor: HOUR_DATA.map(v => {
        if (v < 40) return 'rgba(29,158,117,0.5)'
        if (v < 65) return 'rgba(200,137,58,0.5)'
        return 'rgba(192,80,74,0.5)'
      }),
      borderColor: HOUR_DATA.map(v => {
        if (v < 40) return '#1D9E75'
        if (v < 65) return '#C8893A'
        return '#C0504A'
      }),
      borderWidth: 1,
      borderRadius: 2,
      borderSkipped: false,
    }]
  }

  const sharedYAxis = { min: 0, max: 100, grid: GRID_STYLE, ticks: { ...TICK_STYLE, stepSize: 25 }, border: BORDER_STYLE }
  const sharedXAxis = { grid: { display: false }, ticks: TICK_STYLE, border: BORDER_STYLE }

  const stats = [
    { label: 'Focus Time', value: '5h 20m', sub: '+18 min vs yesterday', color: '#1D9E75' },
    { label: 'Fatigue Peaks', value: '3 today', sub: '2:10 · 4:45 · 6:30 PM', color: '#C8893A' },
    { label: 'Distraction Rate', value: '14%', sub: 'of tracked time', color: '#5B8DB8' },
    { label: 'Best Window', value: '9–11 AM', sub: 'Consistently sharp', color: '#1D9E75' },
  ]

  return (
    <div className="pane">

      {/* ── Stat row ── */}
      <div className="grid-2" style={{ marginBottom: 24 }}>
        {stats.map((s, i) => (
          <div
            key={i}
            className="surf"
            style={{ animationDelay: `${i * 0.05}s`, borderLeft: `1px solid ${s.color}40` }}
          >
            <p className="label">{s.label}</p>
            <div style={{ fontFamily: 'var(--font-serif)', fontSize: 28, fontWeight: 300, letterSpacing: '-0.02em', marginBottom: 4, color: s.color }}>
              {s.value}
            </div>
            <p style={{ fontSize: 11, color: 'var(--text-tertiary)', fontWeight: 300 }}>{s.sub}</p>
          </div>
        ))}
      </div>

      {/* ── Behavior Patterns ── */}
      <div className="card" style={{ marginBottom: 20 }}>
        <p className="label">Derived patterns · 14 days of data</p>
        <div className="patterns-grid">
          {PATTERNS.map((p, i) => (
            <div key={i} className="pattern-item" style={{ animationDelay: `${i * 0.06}s` }}>
              <span className="pattern-icon" style={{ color: p.color }}>{p.icon}</span>
              <div>
                <div className="pattern-title" style={{ color: p.color }}>{p.title}</div>
                <div className="pattern-detail">{p.detail}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Two charts row ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
        {/* Focus decay curve */}
        <div className="surf">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
            <div>
              <p className="label" style={{ margin: 0 }}>Focus decay curve</p>
              <p style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2, fontWeight: 300 }}>Performance vs session length (min)</p>
            </div>
          </div>
          <div style={{ position: 'relative', height: 120 }}>
            <Line
              data={decayData}
              options={{
                ...BASE_CHART,
                plugins: { ...BASE_CHART.plugins, tooltip: { ...BASE_CHART.plugins.tooltip, callbacks: { label: (c: any) => `focus: ${c.raw}%` } } },
                scales: { x: sharedXAxis, y: sharedYAxis }
              }}
            />
          </div>
          <div className="insight-callout">
            <span style={{ color: '#5B8DB8' }}>◈</span>
            <span>Saturation point: <strong>~165 min</strong></span>
          </div>
        </div>

        {/* Burnout trend */}
        <div className="surf">
          <div style={{ marginBottom: 12 }}>
            <p className="label" style={{ margin: 0 }}>Burnout trend · 14 days</p>
            <p style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2, fontWeight: 300 }}>Daily cognitive budget used (%)</p>
          </div>
          <div style={{ position: 'relative', height: 120 }}>
            <Line
              data={burnoutTrendData}
              options={{
                ...BASE_CHART,
                plugins: { ...BASE_CHART.plugins, tooltip: { ...BASE_CHART.plugins.tooltip, callbacks: { label: (c: any) => `burnout: ${c.raw}%` } } },
                scales: { x: sharedXAxis, y: sharedYAxis }
              }}
            />
          </div>
          <div className="insight-callout">
            <span style={{ color: '#C8893A' }}>◈</span>
            <span>Peak risk: <strong>mid-week</strong></span>
          </div>
        </div>
      </div>

      {/* ── Hour heatmap ── */}
      <div className="surf" style={{ marginBottom: 20 }}>
        <div style={{ marginBottom: 12 }}>
          <p className="label" style={{ margin: 0 }}>Daily load heatmap · avg by hour</p>
          <p style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2, fontWeight: 300 }}>
            When your cognitive load peaks across the day
          </p>
        </div>
        <div style={{ position: 'relative', height: 80 }}>
          <Bar
            data={hourHeatmapData}
            options={{
              ...BASE_CHART,
              plugins: { ...BASE_CHART.plugins, tooltip: { ...BASE_CHART.plugins.tooltip, callbacks: { label: (c: any) => `load: ${c.raw}` } } },
              scales: {
                x: { ...sharedXAxis, grid: { display: false } },
                y: { display: false, min: 0, max: 100 }
              }
            }}
          />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8, fontSize: 10, color: 'var(--text-tertiary)', letterSpacing: '0.06em' }}>
          <span>6 AM</span>
          <span style={{ color: '#1D9E75' }}>Peak: 9–11 AM</span>
          <span style={{ color: '#C0504A' }}>High risk: 8–10 PM</span>
          <span>11 PM</span>
        </div>
      </div>

      {/* ── Weekly bar ── */}
      <div className="surf">
        <p className="label">Weekly load pattern</p>
        <div style={{ position: 'relative', height: 140 }}>
          <Bar
            data={weeklyChartData}
            options={{
              ...BASE_CHART,
              plugins: { ...BASE_CHART.plugins, tooltip: { ...BASE_CHART.plugins.tooltip, callbacks: { label: (c: any) => `load: ${c.raw}` } } },
              scales: { x: { ...sharedXAxis }, y: sharedYAxis }
            }}
          />
        </div>
      </div>
    </div>
  )
}
