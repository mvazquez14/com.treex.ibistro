import { createFileRoute } from "@tanstack/react-router"

import { QuoteList } from "@/pages/operations"

export const Route = createFileRoute("/_layout/quotes/")({
  component: QuoteList,
})
