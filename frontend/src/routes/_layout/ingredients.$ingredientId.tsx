import { createFileRoute } from "@tanstack/react-router"

import { IngredientEditor } from "@/pages/resources"

export const Route = createFileRoute("/_layout/ingredients/$ingredientId")({
  component: function Page() {
    const { ingredientId } = Route.useParams()
    return <IngredientEditor ingredientId={ingredientId} />
  },
})
