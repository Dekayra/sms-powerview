import { useEffect, useRef } from "react"

export interface ChartPoint {
  t: number
  v: number
}

interface LineChartProps {
  points: ChartPoint[]
  unit: string
  color: string
  decimals: number
}

/** Minimal canvas line chart with axis labels and a hover tooltip - ported
 * from the original vanilla-JS LineChart class, no charting library. */
export function LineChart({ points, unit, color, decimals }: LineChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const tooltipRef = useRef<HTMLDivElement>(null);
  // xFor is recomputed on every draw() and read by the mousemove handler,
  // so it lives on a ref rather than component state (no need to re-render
  // on every hover-driven recomputation).
  const xForRef = useRef<((t: number) => number) | null>(null)
  const yForRef = useRef<((v: number) => number) | null>(null)

  function bounds() {
    const values = points.map((p) => p.v)
    let min = Math.min(...values)
    let max = Math.max(...values)
    if (min === max) {
      min -= 1
      max += 1
    }
    const pad = (max - min) * 0.15
    return { min: min - pad, max: max + pad }
  }

  function relTime(t: number) {
    const diff = Date.now() / 1000 - t
    if (diff < 90) return "now"
    const mins = Math.round(diff / 60)
    if (mins < 90) return `-${mins}m`
    return `-${Math.round(mins / 60)}h`
  }

  function draw() {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    const rect = canvas.getBoundingClientRect()
    const dpr = window.devicePixelRatio || 1
    canvas.width = Math.max(1, rect.width * dpr)
    canvas.height = Math.max(1, rect.height * dpr)
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    const w = rect.width
    const h = rect.height

    ctx.clearRect(0, 0, w, h)

    if (points.length < 2) {
      ctx.fillStyle = "#9aa0a6"
      ctx.font = "12px system-ui"
      ctx.fillText("Waiting for more data...", 8, h / 2)
      return
    }

    const marginLeft = 44
    const marginBottom = 18
    const marginTop = 6
    const marginRight = 6
    const plotW = w - marginLeft - marginRight
    const plotH = h - marginTop - marginBottom

    const { min, max } = bounds()
    const tMin = points[0].t
    const tMax = points[points.length - 1].t
    const tRange = tMax - tMin || 1

    const xFor = (t: number) => marginLeft + ((t - tMin) / tRange) * plotW
    const yFor = (v: number) => marginTop + plotH - ((v - min) / (max - min)) * plotH

    ctx.strokeStyle = "rgba(128,128,128,.25)"
    ctx.fillStyle = "#9aa0a6"
    ctx.font = "11px system-ui"
    ctx.lineWidth = 1
    ;[min, (min + max) / 2, max].forEach((v) => {
      const y = yFor(v)
      ctx.beginPath()
      ctx.moveTo(marginLeft, y)
      ctx.lineTo(w - marginRight, y)
      ctx.stroke()
      ctx.fillText(v.toFixed(decimals), 2, y + 3)
    })

    ctx.textAlign = "center"
    ;[0, 0.5, 1].forEach((frac) => {
      const t = tMin + frac * tRange
      const x = marginLeft + frac * plotW
      ctx.fillText(relTime(t), Math.min(Math.max(x, marginLeft + 12), w - 12), h - 3)
    })
    ctx.textAlign = "left"

    ctx.beginPath()
    points.forEach((p, i) => {
      const x = xFor(p.t)
      const y = yFor(p.v)
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.strokeStyle = color
    ctx.lineWidth = 2
    ctx.stroke()

    xForRef.current = xFor
    yForRef.current = yFor
  }

  useEffect(() => {
    draw()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points, color, decimals])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const observer = new ResizeObserver(() => draw())
    observer.observe(canvas)
    return () => observer.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function handleMouseMove(e: React.MouseEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current
    const tooltip = tooltipRef.current
    if (!canvas || !tooltip || points.length < 2 || !xForRef.current) return
    const rect = canvas.getBoundingClientRect()
    const x = e.clientX - rect.left

    let nearest = points[0]
    let nearestDist = Infinity
    for (const p of points) {
      const dist = Math.abs(xForRef.current(p.t) - x)
      if (dist < nearestDist) {
        nearestDist = dist
        nearest = p
      }
    }

    tooltip.style.left = `${xForRef.current(nearest.t)}px`
    tooltip.style.top = `${yForRef.current?.(nearest.v) ?? 0}px`
    tooltip.style.opacity = "1"
    const unitSuffix = unit ? ` ${unit}` : ""
    tooltip.textContent = `${nearest.v.toFixed(decimals)}${unitSuffix} - ${new Date(nearest.t * 1000).toLocaleTimeString()}`
  }

  function handleMouseLeave() {
    if (tooltipRef.current) tooltipRef.current.style.opacity = "0"
  }

  return (
    <div className="relative h-40 w-full">
      <canvas
        ref={canvasRef}
        className="h-full w-full"
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
      />
      <div
        ref={tooltipRef}
        className="pointer-events-none absolute -translate-x-1/2 -translate-y-full rounded-md bg-popover px-2 py-1 text-xs text-popover-foreground opacity-0 shadow-md transition-opacity"
      />
    </div>
  )
}
