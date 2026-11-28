import { createFileRoute } from "@tanstack/react-router"

import { ExtraEditor } from "@/pages/extras"

export const Route = createFileRoute("/_layout/menu/extras/$extraId")({
  component: function Page() {
    const { extraId } = Route.useParams()
    return <ExtraEditor extraId={extraId} />
  },
})
