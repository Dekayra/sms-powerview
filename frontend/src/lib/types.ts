export interface StatusField {
  current: string
}

export interface Reading {
  ts?: number
  status: Record<string, StatusField>
  info: Record<string, string>
}

export interface CommandSpec {
  byte0: number
  params: string[]
  danger: "low" | "medium" | "high"
  description: string
}

export type CommandCatalog = Record<string, CommandSpec>

export interface EventEntry {
  ts: number
  field: string
  from: string | null
  to: string
}

export interface IntegrationStatus {
  enabled: boolean
  connected: boolean | null
  host: string | null
  port: number
  discovery_prefix: string
  base_topic: string
  device_id: string
  device_name: string
  last_published: Record<string, { value: string; at: number }>
}

export interface AuthStatus {
  auth_enabled: boolean
  authenticated: boolean
}
