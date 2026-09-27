import type {
  AuthStatus,
  CommandCatalog,
  EventEntry,
  IntegrationStatus,
  Reading,
} from "./types"

class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    ...options,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new ApiError(body.error || `request failed: ${res.status}`, res.status)
  }
  return res.json()
}

export const powerApi = {
  authStatus: () => api<AuthStatus>("/api/auth-status"),
  login: (password: string) =>
    api<{ ok: boolean; error?: string }>("/api/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
  logout: () => api<{ ok: boolean }>("/api/logout", { method: "POST" }),

  history: (since = 0) => api<Reading[]>(`/api/history?since=${since}`),
  events: (since = 0) => api<EventEntry[]>(`/api/events?since=${since}`),
  integration: () => api<IntegrationStatus>("/api/integration"),
  commands: () => api<CommandCatalog>("/api/commands"),
  runCommand: (name: string, params: Record<string, number>, confirm: boolean) =>
    api<{ ok: boolean; error?: string }>("/api/command", {
      method: "POST",
      body: JSON.stringify({ name, params, confirm }),
    }),
  monitor: () => api<Reading>("/monitor"),
}

export { ApiError }
