import { ToastProvider } from "@heroui/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { createRouter, RouterProvider } from "@tanstack/react-router"
import { StrictMode } from "react"
import ReactDOM from "react-dom/client"

import "./index.css"
import { routeTree } from "./routeTree.gen"

const queryClient = new QueryClient()
const router = createRouter({ routeTree, basepath: "/dashboard" })

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}

const root = document.getElementById("root")
if (!root) throw new Error("root")

ReactDOM.createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <ToastProvider placement="bottom" className="!bottom-6" />
    </QueryClientProvider>
  </StrictMode>,
)
