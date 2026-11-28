import { Breadcrumbs } from "@heroui/react"
import type { ReactNode } from "react"

import { Button, Card, CardBody, Switch } from "@/ui/controls"

export function BreadcrumbBar({ crumbs }: { crumbs: string[] }) {
  return (
    <Breadcrumbs className="mb-2">
      {crumbs.map((crumb) => (
        <Breadcrumbs.Item key={crumb}>{crumb}</Breadcrumbs.Item>
      ))}
    </Breadcrumbs>
  )
}

export function EditorLayout({
  crumbs,
  title,
  main,
  side,
}: {
  crumbs: string[]
  title: string
  main: ReactNode
  side: ReactNode
}) {
  return (
    <div className="mx-auto w-full max-w-5xl space-y-6 px-4 py-8 sm:px-6">
      <div>
        <BreadcrumbBar crumbs={crumbs} />
        <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">{title}</h1>
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="flex flex-col gap-6 lg:col-span-8">{main}</div>
        <div className="flex flex-col gap-6 lg:col-span-4">{side}</div>
      </div>
    </div>
  )
}

export function PublishCard({
  active,
  onActive,
  onSave,
  onDiscard,
  saving,
  error,
  showSwitch = true,
}: {
  active?: boolean
  onActive?: (value: boolean) => void
  onSave: () => void
  onDiscard: string
  saving?: boolean
  error?: string
  showSwitch?: boolean
}) {
  return (
    <Card className="border border-zinc-800 bg-zinc-900/90">
      <CardBody className="gap-4">
        <h2 className="text-lg font-semibold">Publicación</h2>
        {showSwitch && onActive ? (
          <Switch isSelected={active} onValueChange={onActive}>
            Activo en micro-landing
          </Switch>
        ) : null}
        {error ? <p className="text-sm text-red-400">{error}</p> : null}
        <div className="grid grid-cols-2 gap-2">
          <Button to={onDiscard} variant="bordered">
            Descartar
          </Button>
          <Button color="primary" onPress={onSave} isLoading={saving}>
            Guardar cambios
          </Button>
        </div>
      </CardBody>
    </Card>
  )
}
