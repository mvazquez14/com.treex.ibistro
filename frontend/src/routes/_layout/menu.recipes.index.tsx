import { createFileRoute } from "@tanstack/react-router"

import { RecipeList } from "@/pages/recipes"

export const Route = createFileRoute("/_layout/menu/recipes/")({
  component: RecipeList,
})
