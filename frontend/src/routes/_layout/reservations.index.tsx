import { createFileRoute } from "@tanstack/react-router"

import { ReservationList } from "@/pages/operations"

export const Route = createFileRoute("/_layout/reservations/")({
  component: ReservationList,
})
