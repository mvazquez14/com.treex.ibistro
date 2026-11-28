import { createFileRoute } from "@tanstack/react-router"

import { PackageList } from "@/pages/packages"

export const Route = createFileRoute("/_layout/menu/packages/")({
  component: PackageList,
})
