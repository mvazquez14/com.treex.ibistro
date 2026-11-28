import { createFileRoute } from "@tanstack/react-router"

import { SupplierList } from "@/pages/resources"

export const Route = createFileRoute("/_layout/suppliers/")({
  component: SupplierList,
})
