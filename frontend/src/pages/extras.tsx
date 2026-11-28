import { Cookie } from "@gravity-ui/icons"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"

import { api, money, patchBody } from "@/api"
import { RowActions } from "@/components/master/RowActions"
import { DataTableCard as MasterTable, SettingsActions as FormActions, SettingsField as FormRow, SettingsSection as FormSection, SettingsSectionForm as SettingsShell, StatusPill } from "@/components/ui-kit"
import { Chip, Input, Select, SelectItem, Switch } from "@/ui/controls"

type Extra = {
  id: string
  name: string
  link_label: string
  unit_price: string
  pricing_type: string
  is_active: boolean
  category_ids?: string[]
  category_names?: string[]
}
type Category = { id: string; name: string }

const PRICING: Record<string, string> = {
  PER_UNIT: "Por unidad",
  PER_GUEST: "Por invitado",
}

export function ExtraList() {
  const query = useQuery({ queryKey: ["extras"], queryFn: () => api<Extra[]>("/menu/extras") })
  const client = useQueryClient()
  return (
    <MasterTable
      crumbs={["Dashboard", "Menú", "Extras"]}
      title="Extras"
      description="Complementos que el cliente suma a la cotización desde la micro-landing."
      rows={query.data ?? []}
      searchText={(row) => `${row.name} ${row.link_label}`}
      createTo="/menu/extras/nuevo"
      createLabel="Nuevo extra"
      columns={[
        { key: "index", label: "#", render: () => null },
        {
          key: "name",
          label: "Nombre",
          render: (row) => (
            <div>
              <p className="text-base font-semibold text-white">{row.name}</p>
              <p className="text-sm text-zinc-400">{PRICING[row.pricing_type] ?? row.link_label}</p>
              <div className="mt-2 flex flex-wrap gap-1">
                {(row.category_names?.length ? row.category_names : ["Todas"]).map((name) => (
                  <Chip key={name} size="sm" variant="soft">
                    {name}
                  </Chip>
                ))}
              </div>
            </div>
          ),
          exportValue: (row) => row.name,
        },
        {
          key: "price",
          label: "Precio",
          render: (row) => <span className="tabular-nums">{money(row.unit_price)}</span>,
          exportValue: (row) => row.unit_price,
        },
        {
          key: "active",
          label: "Estado",
          render: (row) => (
            <div className="flex items-center gap-2">
              <Switch
                size="sm"
                isSelected={row.is_active}
                onValueChange={(value) => {
                  void api(`/menu/extras/${row.id}`, patchBody({ is_active: value })).then(() =>
                    client.invalidateQueries({ queryKey: ["extras"] }),
                  )
                }}
              />
              <StatusPill color={row.is_active ? "success" : "warning"}>
                {row.is_active ? "Activo" : "Inactivo"}
              </StatusPill>
            </div>
          ),
          exportValue: (row) => (row.is_active ? "Activo" : "Inactivo"),
        },
        {
          key: "actions",
          label: "Acciones",
          className: "text-right",
          render: (row) => (
            <RowActions
              editTo={`/menu/extras/${row.id}`}
              summary={<p>{row.name} · {money(row.unit_price)}</p>}
              onDelete={async () => {
                await api(`/menu/extras/${row.id}`, { method: "DELETE" })
                await client.invalidateQueries({ queryKey: ["extras"] })
              }}
            />
          ),
        },
      ]}
    />
  )
}

export function ExtraEditor({ extraId }: { extraId: string }) {
  const isNew = extraId === "nuevo"
  const client = useQueryClient()
  const current = useQuery({
    queryKey: ["extra", extraId],
    queryFn: () => api<Extra[]>("/menu/extras").then((rows) => rows.find((row) => row.id === extraId)),
    enabled: !isNew,
  })
  const [name, setName] = useState("")
  const [price, setPrice] = useState("0")
  const [pricing, setPricing] = useState("PER_UNIT")
  const [active, setActive] = useState(true)
  const [allCategories, setAllCategories] = useState(true)
  const [categoryIds, setCategoryIds] = useState<string[]>([])
  const [error, setError] = useState("")
  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: () => api<Category[]>("/menu/categories"),
  })
  useEffect(() => {
    if (!current.data) return
    const ids = current.data.category_ids ?? []
    setName(current.data.name)
    setPrice(current.data.unit_price)
    setPricing(current.data.pricing_type)
    setActive(current.data.is_active)
    setCategoryIds(ids)
    setAllCategories(ids.length === 0)
  }, [current.data])

  function reset() {
    const ids = current.data?.category_ids ?? []
    setName(current.data?.name ?? "")
    setPrice(current.data?.unit_price ?? "0")
    setPricing(current.data?.pricing_type ?? "PER_UNIT")
    setActive(current.data?.is_active ?? true)
    setCategoryIds(ids)
    setAllCategories(ids.length === 0)
    setError("")
  }

  function toggleCategory(id: string) {
    setAllCategories(false)
    setCategoryIds((currentIds) => {
      const next = currentIds.includes(id) ? currentIds.filter((item) => item !== id) : [...currentIds, id]
      if (next.length === 0) setAllCategories(true)
      return next
    })
  }

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        name,
        unit_price: price,
        pricing_type: pricing,
        is_active: active,
        category_ids: allCategories ? [] : categoryIds,
      }
      if (isNew) return api<Extra>("/menu/extras", { method: "POST", body: JSON.stringify(body) })
      return api<Extra>(`/menu/extras/${extraId}`, patchBody(body))
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["extras"] })
    },
    onError: (reason: Error) => setError(reason.message),
  })

  return (
    <SettingsShell
      icon={<Cookie width={22} height={22} />}
      title={isNew ? "Nuevo extra" : "Editar extra"}
      description="Nombre, forma de cobro y publicación del complemento."
      onReset={reset}
    >
      <FormSection
        title="Información del extra"
        description="El nombre es el que ve el cliente al armar la cotización."
      >
        <FormRow label="Nombre">
          <Input hideLabel label="Nombre" value={name} onValueChange={setName} />
        </FormRow>
      </FormSection>
      <FormSection
        title="Precio"
        description="Puede cobrarse una vez por unidad o multiplicarse por cada invitado."
      >
        <FormRow label="Precio">
          <Input hideLabel label="Precio" value={price} onValueChange={setPrice} />
        </FormRow>
        <FormRow label="Tipo de cobro">
          <Select hideLabel label="Tipo de cobro" selectedKeys={[pricing]} onChange={(event) => setPricing(event.target.value)}>
            <SelectItem id="PER_UNIT">Por unidad</SelectItem>
            <SelectItem id="PER_GUEST">Por invitado</SelectItem>
          </Select>
        </FormRow>
      </FormSection>
      <FormSection
        title="Categorías"
        description="Si eliges todas, el extra aparece en cualquier categoría. Si marcas algunas, solo se ofrece ahí."
      >
        <FormRow label="Dónde aplica">
          <div className="space-y-3 rounded-xl bg-zinc-800/70 p-4">
            <p className="text-sm font-medium text-zinc-200">Categorías donde aplica este extra</p>
            <label className="flex items-center gap-3 text-base text-zinc-100">
              <input
                type="checkbox"
                className="h-5 w-5 accent-accent"
                checked={allCategories}
                onChange={() => {
                  setAllCategories(true)
                  setCategoryIds([])
                }}
              />
              Todas las categorías
            </label>
            {(categories.data ?? []).map((category) => (
              <label key={category.id} className="flex items-center gap-3 text-base text-zinc-100">
                <input
                  type="checkbox"
                  className="h-5 w-5 accent-accent"
                  checked={!allCategories && categoryIds.includes(category.id)}
                  onChange={() => toggleCategory(category.id)}
                />
                {category.name}
              </label>
            ))}
          </div>
        </FormRow>
      </FormSection>
      <FormSection title="Publicación" description="Un extra inactivo deja de ofrecerse en la micro-landing.">
        <FormRow label="Visible">
          <div className="flex items-center gap-3">
            <Switch isSelected={active} onValueChange={setActive}>
              Activo en micro-landing
            </Switch>
            <StatusPill color={active ? "success" : "warning"}>
              {active ? "Activo" : "Inactivo"}
            </StatusPill>
          </div>
        </FormRow>
      </FormSection>
      {error ? <p className="text-sm text-rose-400">{error}</p> : null}
      <FormActions onSave={() => save.mutateAsync()} cancelTo="/menu/extras" saving={save.isPending} />
    </SettingsShell>
  )
}
