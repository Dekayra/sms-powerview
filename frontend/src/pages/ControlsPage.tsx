import { useEffect, useState } from "react"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { CommandButton } from "@/components/CommandButton"
import { powerApi } from "@/lib/api"
import type { CommandCatalog } from "@/lib/types"

const DANGER_VARIANT: Record<string, "secondary" | "outline" | "destructive"> = {
  low: "secondary",
  medium: "outline",
  high: "destructive",
}

export function ControlsPage() {
  const [commands, setCommands] = useState<CommandCatalog>({})
  const [paramValues, setParamValues] = useState<Record<string, number>>({})

  useEffect(() => {
    powerApi.commands().then(setCommands).catch(() => {})
  }, [])

  function paramKey(name: string, param: string) {
    return `${name}.${param}`
  }

  function getParams(name: string, params: string[]): Record<string, number> {
    return Object.fromEntries(params.map((p) => [p, paramValues[paramKey(name, p)] ?? 30]))
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold">Nobreak commands</h2>
        <p className="text-sm text-muted-foreground">
          Low-risk commands run immediately. Anything that affects operation or cuts power asks you
          to confirm first - both here and on the server.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Object.entries(commands).map(([name, spec]) => (
          <Card key={name} className="flex flex-col gap-3 p-4">
            <div className="flex items-center justify-between">
              <strong className="capitalize">{name.replace(/_/g, " ")}</strong>
              <Badge variant={DANGER_VARIANT[spec.danger]}>{spec.danger}</Badge>
            </div>
            <p className="text-sm text-muted-foreground">{spec.description}</p>
            {spec.params.length > 0 && (
              <div className="flex flex-wrap gap-3">
                {spec.params.map((param) => (
                  <div key={param} className="space-y-1">
                    <Label className="text-xs capitalize">{param.replace(/_/g, " ")}</Label>
                    <Input
                      type="number"
                      min={0}
                      max={65535}
                      className="w-24"
                      value={paramValues[paramKey(name, param)] ?? 30}
                      onChange={(e) =>
                        setParamValues((prev) => ({
                          ...prev,
                          [paramKey(name, param)]: parseInt(e.target.value, 10) || 0,
                        }))
                      }
                    />
                  </div>
                ))}
              </div>
            )}
            <CommandButton
              name={name}
              spec={spec}
              params={getParams(name, spec.params)}
              className="mt-auto"
            />
          </Card>
        ))}
      </div>
    </div>
  )
}
