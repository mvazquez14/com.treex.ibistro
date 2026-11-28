import { createFileRoute } from "@tanstack/react-router"

import { RecipeEditor } from "@/pages/recipes"

export const Route = createFileRoute("/_layout/menu/recipes/$recipeId")({
  component: function Page() {
    const { recipeId } = Route.useParams()
    return <RecipeEditor recipeId={recipeId} />
  },
})
