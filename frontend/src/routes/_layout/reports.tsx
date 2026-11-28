import { createFileRoute } from "@tanstack/react-router"

import { ReportsPage } from "@/pages/operations"

export const Route = createFileRoute("/_layout/reports")({
  component: ReportsPage,
})
