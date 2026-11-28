import { createFileRoute } from "@tanstack/react-router"

import { IngredientList } from "@/pages/resources"

export const Route = createFileRoute("/_layout/ingredients/")({
  component: IngredientList,
})
