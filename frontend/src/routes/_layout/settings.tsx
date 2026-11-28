import { createFileRoute } from "@tanstack/react-router"

import { SettingsPage } from "@/pages/operations"

export const Route = createFileRoute("/_layout/settings")({
  component: function Page() {
    const { session } = Route.useRouteContext()
    return (
      <SettingsPage
        name={session.business_name}
        email={session.email}
        billing={session.billing_url}
      />
    )
  },
})
