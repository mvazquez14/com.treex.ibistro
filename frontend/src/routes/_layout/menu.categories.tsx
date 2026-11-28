import { createFileRoute } from "@tanstack/react-router"

import { CategoryList } from "@/pages/resources"

export const Route = createFileRoute("/_layout/menu/categories")({
  component: CategoryList,
})
