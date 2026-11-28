import { createFileRoute } from "@tanstack/react-router"

import { EquipmentList } from "@/pages/resources"

export const Route = createFileRoute("/_layout/equipment/")({
  component: EquipmentList,
})
