import { useRef, useState } from "react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { wsUrl } from "@/lib/ws"

interface SampleMsg {
  type: "sample"
  t: number
  data: { info?: Record<string, string> } | null
  error: string | null
}
interface InstructionMsg {
  type: "instruction"
  text: string
}
interface ErrorMsg {
  type: "error"
  text: string
}
interface DoneMsg {
  type: "done"
}
type DiagMsg = SampleMsg | InstructionMsg | ErrorMsg | DoneMsg

function formatSample(t: number, data: SampleMsg["data"], error: string | null, baseline: string | null) {
  if (error && !data) return `[t=${t}s] error: ${error}`
  if (!data) return `[t=${t}s] no data`

  const byte = data.info?._debug_estado_byte ?? "?"
  const flags = Object.entries(data.info || {})
    .filter(([k]) => !k.startsWith("_"))
    .map(([k, v]) => `${k}=${v}`)
    .join(" ")
  const changed = baseline !== null && byte !== baseline ? "  <-- changed from baseline" : ""
  return `[t=${t}s] byte=${byte}  ${flags}${changed}`
}

/** navigator.clipboard requires a secure context (HTTPS or localhost) -
 * this is typically served over plain HTTP on a LAN address, where it's
 * simply unavailable. Fall back to the old select+execCommand trick,
 * which still works over plain HTTP in every major browser. */
function legacyCopy(text: string): boolean {
  const textarea = document.createElement("textarea")
  textarea.value = text
  textarea.style.position = "fixed"
  textarea.style.opacity = "0"
  document.body.appendChild(textarea)
  textarea.focus()
  textarea.select()
  let ok = false
  try {
    ok = document.execCommand("copy")
  } catch {
    ok = false
  }
  document.body.removeChild(textarea)
  return ok
}

export function DiagnosticsPage() {
  const [transitionDuration, setTransitionDuration] = useState(15)
  const [watchDuration, setWatchDuration] = useState(30)
  const [log, setLog] = useState<string[]>([])
  const [instruction, setInstruction] = useState("")
  const [running, setRunning] = useState<"transition" | "watch" | null>(null)
  const [copyLabel, setCopyLabel] = useState("Copy log to clipboard")
  const baselineRef = useRef<string | null>(null)
  const doneRef = useRef(false)
  const logEndRef = useRef<HTMLPreElement>(null)

  function appendLog(line: string) {
    setLog((prev) => {
      const next = [...prev, line]
      requestAnimationFrame(() => {
        if (logEndRef.current) logEndRef.current.scrollTop = logEndRef.current.scrollHeight
      })
      return next
    })
  }

  function runDiagnostic(mode: "transition" | "watch", duration: number) {
    setLog([])
    setInstruction("")
    baselineRef.current = null
    doneRef.current = false
    setRunning(mode)

    const ws = new WebSocket(wsUrl("/ws/diagnostics"))
    ws.onopen = () => ws.send(JSON.stringify({ mode, duration }))

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data) as DiagMsg
      if (msg.type === "sample") {
        if (msg.t === 0) baselineRef.current = msg.data?.info?._debug_estado_byte ?? null
        appendLog(formatSample(msg.t, msg.data, msg.error, baselineRef.current))
      } else if (msg.type === "instruction") {
        setInstruction(msg.text)
        appendLog(`--- ${msg.text} ---`)
      } else if (msg.type === "error") {
        appendLog(`ERROR: ${msg.text}`)
      } else if (msg.type === "done") {
        doneRef.current = true
        appendLog("--- done - copy the log above and paste it back ---")
      }
    }

    // The connection closing right after "done" is expected, not a
    // failure - only surface onerror as an actual problem if it happens
    // before that.
    ws.onerror = () => {
      if (!doneRef.current) appendLog("websocket error (connection dropped before the run finished)")
    }
    ws.onclose = () => setRunning(null)
  }

  async function handleCopy() {
    const text = log.join("\n")
    let ok = false

    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text)
        ok = true
      } catch {
        ok = false
      }
    }
    if (!ok) ok = legacyCopy(text)

    if (ok) {
      setCopyLabel("Copied!")
      setTimeout(() => setCopyLabel("Copy log to clipboard"), 1500)
    } else {
      alert("Couldn't copy automatically - select the log text above and copy manually.")
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-lg font-semibold">Diagnostics</h2>
        <p className="text-sm text-muted-foreground">
          Real hardware doesn't fully match this protocol's documented status bits (see README).
          These sample the raw status byte once a second instead of waiting on the normal poll
          interval, and log everything below so you can just copy it.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Card className="flex flex-col gap-3 p-4">
          <strong>Test transition</strong>
          <p className="text-sm text-muted-foreground">
            Runs a short battery test itself and watches which status bits change, once a second.
          </p>
          <div className="space-y-1">
            <Label className="text-xs">duration (s)</Label>
            <Input
              type="number"
              min={5}
              max={120}
              className="w-24"
              value={transitionDuration}
              onChange={(e) => setTransitionDuration(parseInt(e.target.value, 10) || 15)}
            />
          </div>
          <Button
            className="mt-auto"
            disabled={running !== null}
            onClick={() => runDiagnostic("transition", transitionDuration)}
          >
            Run
          </Button>
        </Card>

        <Card className="flex flex-col gap-3 p-4">
          <strong>Watch mode</strong>
          <p className="text-sm text-muted-foreground">
            Sends no command - just watches. Trigger the event yourself (e.g. briefly unplug AC
            power) as soon as it says to.
          </p>
          <div className="space-y-1">
            <Label className="text-xs">duration (s)</Label>
            <Input
              type="number"
              min={5}
              max={120}
              className="w-24"
              value={watchDuration}
              onChange={(e) => setWatchDuration(parseInt(e.target.value, 10) || 30)}
            />
          </div>
          <Button
            className="mt-auto"
            disabled={running !== null}
            onClick={() => runDiagnostic("watch", watchDuration)}
          >
            Run
          </Button>
        </Card>
      </div>

      <div>
        <div className="mb-2 flex flex-col gap-1">
          <h2 className="text-lg font-semibold">Log</h2>
          <span className="text-xs text-muted-foreground">{instruction}</span>
        </div>
        <pre ref={logEndRef} className="max-h-96 overflow-y-auto rounded-lg border bg-card p-4 text-xs">
          {log.length ? log.join("\n") : "Nothing run yet."}
        </pre>
        <Button variant="ghost" size="sm" className="mt-2" onClick={handleCopy}>
          {copyLabel}
        </Button>
      </div>
    </div>
  )
}
