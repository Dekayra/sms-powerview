import { useState } from "react"
import { Button } from "@/components/ui/button"
import { powerApi } from "@/lib/api"
import type { CommandSpec } from "@/lib/types"

const DANGER_WARNINGS: Record<string, string> = {
  medium: "This will affect the nobreak's operation (e.g. running on battery).",
  high: "This will CUT OUTPUT POWER to everything plugged into the nobreak.",
}

interface CommandButtonProps {
  name: string
  spec: CommandSpec
  params?: Record<string, number>
  label?: string
  className?: string
}

/** Sends a command, with visible in-button feedback (disabled while in
 * flight, then a brief "Sent"/"Failed" state) instead of a silent request. */
export function CommandButton({ name, spec, params = {}, label, className }: CommandButtonProps) {
  const [state, setState] = useState<"idle" | "sending" | "sent" | "failed">("idle")

  async function handleClick() {
    if (spec.danger !== "low") {
      const warning = DANGER_WARNINGS[spec.danger] || ""
      const displayLabel = name.replace(/_/g, " ")
      if (!window.confirm(`${warning}\n\nRun "${displayLabel}"?`)) return
    }

    setState("sending")
    let ok = false
    let errorMessage = ""
    try {
      const result = await powerApi.runCommand(name, params, spec.danger !== "low")
      ok = result.ok
      if (!ok) errorMessage = result.error || "unknown error"
    } catch (err) {
      errorMessage = err instanceof Error ? err.message : String(err)
    }

    setState(ok ? "sent" : "failed")
    if (!ok) alert(`"${name.replace(/_/g, " ")}" failed: ${errorMessage}`)

    setTimeout(() => setState("idle"), 1800)
  }

  const text =
    state === "sending" ? "Sending…" : state === "sent" ? "Sent ✓" : state === "failed" ? "Failed" : label || "Run"

  return (
    <Button
      size="sm"
      variant={spec.danger === "high" ? "destructive" : spec.danger === "medium" ? "outline" : "secondary"}
      disabled={state === "sending"}
      onClick={handleClick}
      className={className}
    >
      {text}
    </Button>
  )
}
