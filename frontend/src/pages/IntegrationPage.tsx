import { useEffect, useState } from "react"
import { Card } from "@/components/ui/card"
import { powerApi } from "@/lib/api"
import type { IntegrationStatus } from "@/lib/types"
import { cn } from "@/lib/utils"

function fmtTime(epochSeconds: number) {
  return new Date(epochSeconds * 1000).toLocaleString()
}

export function IntegrationPage() {
  const [data, setData] = useState<IntegrationStatus | null>(null)

  useEffect(() => {
    function load() {
      powerApi.integration().then(setData).catch(() => {})
    }
    load()
    const interval = setInterval(load, 10000)
    return () => clearInterval(interval)
  }, [])

  const rows = data ? Object.entries(data.last_published).sort(([a], [b]) => a.localeCompare(b)) : []

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h2 className="text-lg font-semibold">Home Assistant / MQTT integration</h2>
        <p className="text-sm text-muted-foreground">Read-only. Configure MQTT via .env - see the README.</p>
      </div>

      {!data && <p className="text-sm text-muted-foreground">Loading…</p>}

      {data && (
        <section className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Card className={cn("p-4", data.enabled ? (data.connected ? "border-success/40 bg-success/5" : "") : "border-muted")}>
            <div className="text-xs font-medium text-muted-foreground">MQTT enabled</div>
            <div className="mt-1 text-2xl font-semibold">{data.enabled ? "Yes" : "No"}</div>
          </Card>
          <Card className={cn("p-4", data.connected ? "border-success/40 bg-success/5" : "border-muted")}>
            <div className="text-xs font-medium text-muted-foreground">Connected</div>
            <div className="mt-1 text-2xl font-semibold">
              {data.connected === null ? "n/a" : data.connected ? "Yes" : "No"}
            </div>
          </Card>
          <Card className="p-4">
            <div className="text-xs font-medium text-muted-foreground">Broker</div>
            <div className="mt-1 text-base font-semibold">{data.host ? `${data.host}:${data.port}` : "-"}</div>
          </Card>
          <Card className="p-4">
            <div className="text-xs font-medium text-muted-foreground">Base topic</div>
            <div className="mt-1 text-base font-semibold">{data.base_topic}</div>
          </Card>
          <Card className="p-4">
            <div className="text-xs font-medium text-muted-foreground">Discovery prefix</div>
            <div className="mt-1 text-base font-semibold">{data.discovery_prefix}</div>
          </Card>
          <Card className="p-4">
            <div className="text-xs font-medium text-muted-foreground">Device</div>
            <div className="mt-1 text-base font-semibold">{data.device_name}</div>
          </Card>
        </section>
      )}

      <section>
        <h2 className="mb-3 text-lg font-semibold">Last published values</h2>
        <Card className="overflow-hidden p-0">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-2 font-medium">Topic</th>
                <th className="px-4 py-2 font-medium">Value</th>
                <th className="px-4 py-2 font-medium">At</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {rows.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-4 py-4 text-muted-foreground">
                    Nothing published yet.
                  </td>
                </tr>
              )}
              {rows.map(([topic, v]) => (
                <tr key={topic}>
                  <td className="px-4 py-2 font-mono text-xs">{topic}</td>
                  <td className="px-4 py-2">{v.value}</td>
                  <td className="px-4 py-2 text-xs text-muted-foreground">{fmtTime(v.at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </section>
    </div>
  )
}
