import { createFileRoute } from "@tanstack/react-router"

import { RuleList } from "@/pages/resources"

export const Route = createFileRoute("/_layout/equipment/rules")({
  component: RuleList,
})
