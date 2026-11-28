import { createFileRoute, Outlet, redirect } from "@tanstack/react-router"

import { getSession } from "@/api"
import { AppShell } from "@/components/shell/AppShell"

export const Route = createFileRoute("/_layout")({
  beforeLoad: async () => {
    const session = await getSession()
    if (!session.authenticated) {
      window.location.href = "/login"
      throw redirect({ href: "/login" })
    }
    if (session.is_superuser && !session.impersonating) {
      window.location.href = "/admin"
      throw redirect({ href: "/admin" })
    }
    if (session.onboarding_completed === false) {
      throw redirect({ to: "/onboarding" })
    }
    return { session }
  },
  component: function Layout() {
    const { session } = Route.useRouteContext()
    return (
      <AppShell session={session}>
        <Outlet />
      </AppShell>
    )
  },
})
