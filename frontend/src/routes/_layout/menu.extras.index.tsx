import { createFileRoute } from "@tanstack/react-router"

import { ExtraList } from "@/pages/extras"

export const Route = createFileRoute("/_layout/menu/extras/")({
  component: ExtraList,
})
