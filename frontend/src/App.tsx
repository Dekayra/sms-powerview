import { BrowserRouter, Routes, Route } from "react-router-dom"
import { AuthProvider, useAuth } from "@/lib/auth-context"
import { LoginPage } from "@/pages/LoginPage"
import { Layout } from "@/components/Layout"
import { DashboardPage } from "@/pages/DashboardPage"
import { ControlsPage } from "@/pages/ControlsPage"
import { IntegrationPage } from "@/pages/IntegrationPage"
import { JsonPage } from "@/pages/JsonPage"
import { DiagnosticsPage } from "@/pages/DiagnosticsPage"

function Gate() {
  const { loading, authenticated } = useAuth()

  if (loading) {
    return <div className="flex min-h-screen items-center justify-center text-muted-foreground">Loading…</div>
  }

  if (!authenticated) {
    return <LoginPage />
  }

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="controls" element={<ControlsPage />} />
        <Route path="integration" element={<IntegrationPage />} />
        <Route path="json" element={<JsonPage />} />
        <Route path="diagnostics" element={<DiagnosticsPage />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Gate />
      </AuthProvider>
    </BrowserRouter>
  )
}
