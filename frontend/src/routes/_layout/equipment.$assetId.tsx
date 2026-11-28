import { createFileRoute } from "@tanstack/react-router"

import { EquipmentEditor } from "@/pages/resources"

export const Route = createFileRoute("/_layout/equipment/$assetId")({
  component: function Page() {
    const { assetId } = Route.useParams()
    return <EquipmentEditor assetId={assetId} />
  },
})
