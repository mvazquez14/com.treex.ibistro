import { createFileRoute } from "@tanstack/react-router"

import type { Session } from "@/api"
import { ExecutiveDashboard } from "@/pages/dashboard"

export const Route = createFileRoute("/_layout/")({
  component: function Home() {
    const { session } = Route.useRouteContext() as { session: Session }
    return <ExecutiveDashboard session={session} />
  },
})
