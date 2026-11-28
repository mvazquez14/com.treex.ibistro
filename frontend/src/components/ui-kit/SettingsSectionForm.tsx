import { toast } from "@heroui/react"
import { useNavigate } from "@tanstack/react-router"
import type { ReactNode } from "react"

import { Button } from "@/ui/controls"

type ListRoute =
  | "/"
  | "/menu/recipes"
  | "/menu/packages"
  | "/menu/extras"
  | "/warehouses"
  | "/ingredients"
  | "/suppliers"
  | "/equipment"

export function SettingsSectionForm({
  icon,
  title,
  description,
  onReset,
  action,
  widthClassName = "max-w-5xl",
  children,
}: {
  icon: ReactNode
  title: string
  description: string
  onReset: () => void
  action?: ReactNode
  widthClassName?: string
  children: ReactNode
}) {
  return (
    <div className={`mx-auto w-full space-y-6 px-4 py-8 sm:px-6 ${widthClassName}`}>
      <div className="flex flex-col gap-4 rounded-2xl border border-zinc-800/80 bg-background-secondary p-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-4">
          <span className="grid size-12 shrink-0 place-items-center rounded-full bg-accent text-accent-foreground">
            {icon}
          </span>
          <div>
            <h1 className="text-5xl font-bold leading-none text-white">{title}</h1>
            <p className="mt-1 text-base text-zinc-400">{description}</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <button type="button" className="text-sm font-medium text-accent" onClick={onReset}>
            Restablecer
          </button>
          {action}
        </div>
      </div>
      <div className="rounded-2xl border border-zinc-800/80 bg-background-secondary px-6">{children}</div>
    </div>
  )
}

export function SettingsSection({
  title,
  description,
  children,
}: {
  title: string
  description: string
  children: ReactNode
}) {
  return (
    <section className="grid grid-cols-1 gap-8 border-b border-zinc-800/80 py-8 lg:grid-cols-12">
      <div className="lg:col-span-4">
        <h2 className="text-4xl font-semibold leading-[1.11] text-white">{title}</h2>
        <p className="mt-1 text-sm leading-relaxed text-zinc-400">{description}</p>
      </div>
      <div className="space-y-5 lg:col-span-8">{children}</div>
    </section>
  )
}

export function SettingsField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-1 items-center gap-4 sm:grid-cols-12">
      <span className="text-sm font-medium text-zinc-200 sm:col-span-4">{label}</span>
      <div className="min-w-0 sm:col-span-8">{children}</div>
    </div>
  )
}

export function SettingsActions({
  onSave,
  cancelTo,
  saving,
}: {
  onSave: () => Promise<unknown>
  cancelTo: ListRoute
  saving?: boolean
}) {
  const navigate = useNavigate()
  async function save() {
    try {
      await onSave()
      toast.success("Cambios guardados", {
        description: "La información se actualizó correctamente.",
        timeout: 4000,
      })
      await navigate({ to: cancelTo })
    } catch (reason) {
      const description = reason instanceof Error ? reason.message : "No se pudo guardar"
      toast.danger("Error al guardar", { description, timeout: 4000 })
    }
  }
  return (
    <div className="grid grid-cols-1 py-6 lg:grid-cols-12">
      <div className="flex items-center gap-3 lg:col-span-8 lg:col-start-5">
        <Button className="bg-accent font-semibold text-accent-foreground" onPress={() => void save()} isLoading={saving}>
          Guardar cambios
        </Button>
        <Button variant="flat" onPress={() => void navigate({ to: cancelTo })}>
          Cancelar
        </Button>
      </div>
    </div>
  )
}
