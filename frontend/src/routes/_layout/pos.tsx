import { createFileRoute } from "@tanstack/react-router"

import { PosPage } from "@/pages/operations"

export const Route = createFileRoute("/_layout/pos")({
  component: PosPage,
})
