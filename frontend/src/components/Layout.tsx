import { useState } from "react"
import { NavLink, Outlet } from "react-router-dom"
import { LogOut, Menu, Zap } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet"
import { useAuth } from "@/lib/auth-context"
import { cn } from "@/lib/utils"

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/controls", label: "Controls" },
  { to: "/integration", label: "Integration" },
  { to: "/json", label: "JSON" },
  { to: "/diagnostics", label: "Diagnostics" },
]

export function Layout() {
  const { authEnabled, logout } = useAuth()
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    // h-dvh + the document itself never scrolls, only <main> does. iOS
    // Safari's document-level scroll is what drives pull-to-refresh and
    // desyncs position:fixed elements when the address bar
    // collapses/expands mid-scroll - making the document non-scrollable
    // removes both problems at the source instead of patching around them.
    <div className="flex h-dvh flex-col overflow-hidden bg-background">
      <nav className="h-14 shrink-0 border-b bg-background">
        <div className="mx-auto flex h-full max-w-6xl items-center gap-4 px-4">
          <NavLink to="/" className="flex items-center gap-2 font-semibold">
            <Zap className="size-5 text-primary" />
            <span className="hidden sm:inline">SMS Nobreak Reader</span>
            <span className="sm:hidden">SMS Reader</span>
          </NavLink>

          {/* Desktop nav */}
          <div className="hidden flex-1 gap-1 md:flex">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    "rounded-md px-3 py-1.5 text-sm font-medium transition-colors hover:bg-accent",
                    isActive && "bg-primary text-primary-foreground hover:bg-primary/90",
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </div>
          <div className="flex-1 md:hidden" />

          {authEnabled && (
            <Button
              variant="ghost"
              size="sm"
              className="hidden gap-1.5 md:inline-flex"
              onClick={() => logout()}
            >
              <LogOut className="size-3.5" />
              Log out
            </Button>
          )}

          {/* Mobile hamburger */}
          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="shrink-0 md:hidden" aria-label="Abrir menu">
                <Menu className="size-5" />
              </Button>
            </SheetTrigger>
            <SheetContent side="right" className="w-72">
              <SheetHeader>
                <SheetTitle className="flex items-center gap-2">
                  <Zap className="size-5 text-primary" />
                  SMS Nobreak Reader
                </SheetTitle>
              </SheetHeader>
              <div className="flex flex-col gap-1 px-4">
                {NAV_ITEMS.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.end}
                    onClick={() => setMobileOpen(false)}
                    className={({ isActive }) =>
                      cn(
                        "rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-accent",
                        isActive && "bg-primary text-primary-foreground hover:bg-primary/90",
                      )
                    }
                  >
                    {item.label}
                  </NavLink>
                ))}
                {authEnabled && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="mt-2 justify-start gap-1.5"
                    onClick={() => {
                      setMobileOpen(false)
                      logout()
                    }}
                  >
                    <LogOut className="size-3.5" />
                    Log out
                  </Button>
                )}
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </nav>
      <main className="min-h-0 flex-1 overflow-y-auto overscroll-contain [-webkit-overflow-scrolling:touch]">
        <div className="mx-auto max-w-6xl px-4 pb-6 pt-4">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
