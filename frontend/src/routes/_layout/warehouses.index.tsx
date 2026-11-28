import { createFileRoute } from "@tanstack/react-router"

import { WarehouseList } from "@/pages/resources"

export const Route = createFileRoute("/_layout/warehouses/")({
  component: WarehouseList,
})
