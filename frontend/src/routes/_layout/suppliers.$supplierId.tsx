import { createFileRoute } from "@tanstack/react-router"

import { SupplierEditor } from "@/pages/resources"

export const Route = createFileRoute("/_layout/suppliers/$supplierId")({
  component: function Page() {
    const { supplierId } = Route.useParams()
    return <SupplierEditor supplierId={supplierId} />
  },
})
