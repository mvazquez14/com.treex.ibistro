import { createFileRoute } from "@tanstack/react-router"

import { GroupList } from "@/pages/resources"

export const Route = createFileRoute("/_layout/menu/groups")({
  component: GroupList,
})
