import { useEffect, useRef } from 'react'

interface GaugeProps {
  score: number
}

export function GaugeCanvas({ score }: GaugeProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const c = canvasRef.current
    if (!c) return
    const ctx = c.getContext('2d')!
    const dpr = window.devicePixelRatio || 1
    const w = 160, h = 90
    c.width = w * dpr
    c.height = h * dpr
    c.style.width = w + 'px'
    c.style.height = h + 'px'
    ctx.scale(dpr, dpr)

    ctx.clearRect(0, 0, w, h)

    const cx = 80, cy = 82, r = 62

    // Track
    ctx.lineCap = 'round'
    ctx.lineWidth = 8
    ctx.beginPath()
    ctx.arc(cx, cy, r, Math.PI, 2 * Math.PI)
    ctx.strokeStyle = 'rgba(255,255,255,0.06)'
    ctx.stroke()

    // Arc color
    const arc = score < 40 ? '#1D9E75' : score < 65 ? '#C8893A' : '#C0504A'
    const scoreEnd = Math.PI + (score / 100) * Math.PI

    ctx.beginPath()
    ctx.arc(cx, cy, r, Math.PI, scoreEnd)
    ctx.strokeStyle = arc
    ctx.lineWidth = 8
    ctx.stroke()

    // Glow
    ctx.shadowBlur = 12
    ctx.shadowColor = arc
    ctx.beginPath()
    ctx.arc(cx, cy, r, Math.PI, scoreEnd)
    ctx.stroke()
    ctx.shadowBlur = 0

    // Labels
    ctx.fillStyle = 'rgba(232,228,220,0.2)'
    ctx.font = '300 10px "DM Mono", monospace'
    ctx.textAlign = 'left'
    ctx.fillText('0', 10, 82)
    ctx.textAlign = 'right'
    ctx.fillText('100', 150, 82)
  }, [score])

  return (
    <canvas
      ref={canvasRef}
      aria-label={`Cognitive load gauge: ${score}`}
      style={{ display: 'block', margin: '0 auto' }}
    />
  )
}
