import { useEffect, useRef, useState } from "react"
import { Card } from "@/components/ui/card"
import { LineChart, type ChartPoint } from "@/components/LineChart"
import { powerApi } from "@/lib/api"
import { wsUrl } from "@/lib/ws"
import type { EventEntry, Reading } from "@/lib/types"
import { cn } from "@/lib/utils"

const METRICS = [
  { key: "input_voltage", label: "Input Voltage", unit: "V", decimals: 1, color: "#1565c0" },
  { key: "output_voltage", label: "Output Voltage", unit: "V", decimals: 1, color: "#2e7d32" },
  { key: "output_frequency", label: "Output Frequency", unit: "Hz", decimals: 1, color: "#6a1b9a" },
  { key: "battery_charge", label: "Battery Charge", unit: "%", decimals: 1, color: "#f9a825" },
  { key: "temperature", label: "Temperature", unit: "°C", decimals: 1, color: "#c62828" },
  { key: "output_power", label: "Output Power", unit: "W", decimals: 1, color: "#00838f" },
] as const

// battery_in_use and self_test_active are confirmed against real hardware
// (see reader.py); the rest are untested best-effort guesses.
const INFO_FIELDS = [
  "battery_in_use",
  "battery_connected",
  "battery_low",
  "self_test_active",
  "ups_ok",
  "status_bit_5",
  "shutdown_active",
]

function fmtTime(epochSeconds: number) {
  return new Date(epochSeconds * 1000).toLocaleString()
}

export function DashboardPage() {
  const [reading, setReading] = useState<Reading | null>(null)
  const [readError, setReadError] = useState<string | null>(null)
  const [series, setSeries] = useState<Record<string, ChartPoint[]>>(() =>
    Object.fromEntries(METRICS.map((m) => [m.key, []])),
  )
  const [events, setEvents] = useState<EventEntry[]>([])
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    let cancelled = false

    async function loadHistory() {
      const entries = await powerApi.history()
      if (cancelled) return
      const next: Record<string, ChartPoint[]> = Object.fromEntries(METRICS.map((m) => [m.key, []]))
      for (const entry of entries) {
        for (const m of METRICS) {
          const v = parseFloat(entry.status?.[m.key]?.current)
          if (!isNaN(v) && entry.ts !== undefined) next[m.key].push({ t: entry.ts, v })
        }
      }
      setSeries(next)
      if (entries.length) setReading(entries[entries.length - 1])
    }

    async function loadEvents() {
      const evs = await powerApi.events()
      if (!cancelled) setEvents(evs)
    }

    loadHistory().catch(() => {})
    loadEvents().catch(() => {})
    const eventsInterval = setInterval(() => loadEvents().catch(() => {}), 30000)

    function connectWs() {
      const ws = new WebSocket(wsUrl("/ws"))
      wsRef.current = ws
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data)
        if (msg.error && !msg.data) {
          setReadError("Couldn't read the nobreak: " + msg.error)
        } else {
          setReadError(null)
          setReading(msg.data)
        }
        if (msg.data) {
          const t = Date.now() / 1000
          setSeries((prev) => {
            const next = { ...prev }
            for (const m of METRICS) {
              const v = parseFloat(msg.data.status?.[m.key]?.current)
              if (!isNaN(v)) next[m.key] = [...next[m.key], { t, v }]
            }
            return next
          })
        }
      }
      ws.onclose = () => {
        if (!cancelled) reconnectTimer.current = setTimeout(connectWs, 3000)
      }
      ws.onerror = () => ws.close()
    }
    connectWs()

    return () => {
      cancelled = true
      clearInterval(eventsInterval)
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [])

  return (
    <div className="flex flex-col gap-8">
      {readError && (
        <p className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-2 text-sm text-destructive">
          {readError}
        </p>
      )}

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {METRICS.map((m) => {
          const v = reading?.status?.[m.key]?.current
          return (
            <Card key={m.key} className="p-4">
              <div className="text-xs font-medium text-muted-foreground">{m.label}</div>
              <div className="mt-1 text-2xl font-semibold">
                {v ?? "--"}
                <span className="ml-0.5 text-sm font-normal text-muted-foreground">{m.unit}</span>
              </div>
            </Card>
          )
        })}
        {INFO_FIELDS.map((key) => {
          const v = reading?.info?.[key]
          return (
            <Card
              key={key}
              className={cn(
                "p-4",
                v === "On" && "border-success/40 bg-success/5",
                v === "Off" && "border-muted",
              )}
            >
              <div className="text-xs font-medium capitalize text-muted-foreground">
                {key.replace(/_/g, " ")}
              </div>
              <div className="mt-1 text-2xl font-semibold">{v ?? "--"}</div>
            </Card>
          )
        })}
      </section>

      <section>
        <div className="mb-3 flex flex-col gap-1">
          <h2 className="text-lg font-semibold">History - last 24h</h2>
          <span className="text-xs text-muted-foreground">
            Hover a chart for exact values. Charts start filling in as soon as the app runs; nothing
            is backfilled from the nobreak itself.
          </span>
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {METRICS.map((m) => (
            <Card key={m.key} className="p-4">
              <h3 className="mb-2 text-sm font-medium">
                {m.label} ({m.unit})
              </h3>
              <LineChart points={series[m.key]} unit={m.unit} color={m.color} decimals={m.decimals} />
            </Card>
          ))}
        </div>
      </section>

      <section>
        <div className="mb-3 flex flex-col gap-1">
          <h2 className="text-lg font-semibold">Recent events</h2>
          <span className="text-xs text-muted-foreground">
            State changes (e.g. switching to battery, bypass) in the retained window.
          </span>
        </div>
        <Card className="divide-y p-0">
          {events.length === 0 && (
            <p className="p-4 text-sm text-muted-foreground">No state changes recorded yet.</p>
          )}
          {events.slice(0, 50).map((e, i) => (
            <div key={i} className="flex items-center gap-3 px-4 py-2.5 text-sm">
              <span className="w-40 shrink-0 text-xs text-muted-foreground">{fmtTime(e.ts)}</span>
              <span>
                {e.field.replace(/_/g, " ")}: {e.from ?? "?"} &rarr; {e.to}
              </span>
            </div>
          ))}
        </Card>
      </section>
    </div>
  )
}
