import { createFileRoute } from "@tanstack/react-router"

import { PackageEditor } from "@/pages/packages"

export const Route = createFileRoute("/_layout/menu/packages/$packageId")({
  component: function Page() {
    const { packageId } = Route.useParams()
    return <PackageEditor packageId={packageId} />
  },
})
