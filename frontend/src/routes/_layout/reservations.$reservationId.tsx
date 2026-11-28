import { createFileRoute } from "@tanstack/react-router"

import { ReservationEditor } from "@/pages/operations"

export const Route = createFileRoute("/_layout/reservations/$reservationId")({
  component: function Page() {
    const { reservationId } = Route.useParams()
    return <ReservationEditor reservationId={reservationId} />
  },
})
