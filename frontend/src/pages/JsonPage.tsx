import { useEffect, useState } from "react"
import { powerApi } from "@/lib/api"

export function JsonPage() {
  const [text, setText] = useState("loading...")

  useEffect(() => {
    function load() {
      powerApi
        .monitor()
        .then((body) => setText(JSON.stringify(body, null, 2)))
        .catch((err) => setText(JSON.stringify({ error: err.message }, null, 2)))
    }
    load()
    const interval = setInterval(load, 5000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold">Raw JSON</h2>
        <p className="text-sm text-muted-foreground">
          Same data as <code className="rounded bg-muted px-1 py-0.5">GET /monitor</code>{" "}
          (unauthenticated, for Home Assistant's REST integration or anything else without a login
          flow). This page just refreshes it for you.
        </p>
      </div>
      <pre className="overflow-x-auto rounded-lg border bg-card p-4 text-xs">{text}</pre>
    </div>
  )
}
