import { createFileRoute } from "@tanstack/react-router"

import { QuoteEditor } from "@/pages/operations"

export const Route = createFileRoute("/_layout/quotes/$quoteId")({
  component: function Page() {
    const { quoteId } = Route.useParams()
    return <QuoteEditor quoteId={quoteId} />
  },
})
