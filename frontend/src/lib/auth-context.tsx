import { createContext, useContext, useEffect, useState, type ReactNode } from "react"
import { powerApi } from "@/lib/api"

interface AuthContextValue {
  loading: boolean
  authEnabled: boolean
  authenticated: boolean
  login: (password: string) => Promise<{ ok: boolean; error?: string }>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true)
  const [authEnabled, setAuthEnabled] = useState(false)
  const [authenticated, setAuthenticated] = useState(false)

  async function refresh() {
    try {
      const status = await powerApi.authStatus()
      setAuthEnabled(status.auth_enabled)
      setAuthenticated(status.authenticated)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  async function login(password: string) {
    const result = await powerApi.login(password)
    if (result.ok) {
      setAuthenticated(true)
    }
    return result
  }

  async function logout() {
    await powerApi.logout()
    setAuthenticated(false)
  }

  return (
    <AuthContext.Provider value={{ loading, authEnabled, authenticated, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
