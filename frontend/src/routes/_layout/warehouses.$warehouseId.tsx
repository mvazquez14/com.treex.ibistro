import { createFileRoute } from "@tanstack/react-router"

import { WarehouseEditor } from "@/pages/resources"

export const Route = createFileRoute("/_layout/warehouses/$warehouseId")({
  component: function Page() {
    const { warehouseId } = Route.useParams()
    return <WarehouseEditor warehouseId={warehouseId} />
  },
})
