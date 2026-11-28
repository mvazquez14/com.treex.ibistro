import { Box as PackageIcon } from "@gravity-ui/icons"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import { api, money, patchBody } from "@/api"
import { RowActions } from "@/components/master/RowActions"
import { DataTableCard as MasterTable, SettingsActions as FormActions, SettingsField as FormRow, SettingsSection as FormSection, SettingsSectionForm as SettingsShell, StatusPill } from "@/components/ui-kit"
import { LogoDropZone } from "@/pages/onboarding-dropzone"
import { Avatar, Chip, Input, Select, SelectItem, Switch, Textarea } from "@/ui/controls"

type Group = {
  id: string
  group_name: string
  min_choices: number
  max_choices: number
  options: { id: string; recipe_id: string; recipe_name: string }[]
}
type RecipeOption = { id: string; name: string }

function VariantGroupCard({
  group,
  recipes,
  optionRecipe,
  onOptionRecipe,
  onChanged,
  onError,
}: {
  group: Group
  recipes: RecipeOption[]
  optionRecipe: string
  onOptionRecipe: (value: string) => void
  onChanged: () => Promise<unknown>
  onError: (message: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(group.group_name)
  const [minChoices, setMinChoices] = useState(String(group.min_choices))
  const [maxChoices, setMaxChoices] = useState(String(group.max_choices))
  const [saving, setSaving] = useState(false)

  function beginEdit() {
    setName(group.group_name)
    setMinChoices(String(group.min_choices))
    setMaxChoices(String(group.max_choices))
    setEditing(true)
  }

  async function saveGroup() {
    setSaving(true)
    onError("")
    try {
      await api(
        `/menu/groups/${group.id}`,
        patchBody({
          group_name: name,
          min_choices: Number(minChoices),
          max_choices: Number(maxChoices),
        }),
      )
      setEditing(false)
      await onChanged()
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "No se pudo guardar el grupo")
    } finally {
      setSaving(false)
    }
  }

  async function removeGroup() {
    setSaving(true)
    onError("")
    try {
      for (const option of group.options) {
        await api(`/menu/options/${option.id}`, { method: "DELETE" })
      }
      await api(`/menu/groups/${group.id}`, { method: "DELETE" })
      await onChanged()
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "No se pudo quitar el grupo")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-3 rounded-xl bg-zinc-800/40 p-4">
      {editing ? (
        <div className="space-y-3">
          <Input hideLabel label="Nombre del grupo" value={name} onValueChange={setName} />
          <div className="grid gap-3 sm:grid-cols-2">
            <Input hideLabel label="Mínimo" type="number" value={minChoices} onValueChange={setMinChoices} />
            <Input hideLabel label="Máximo" type="number" value={maxChoices} onValueChange={setMaxChoices} />
          </div>
          <div className="flex gap-3">
            <button
              type="button"
              className="rounded-full bg-accent px-5 py-2 text-sm font-semibold text-accent-foreground disabled:opacity-60"
              disabled={saving}
              onClick={() => void saveGroup()}
            >
              Guardar grupo
            </button>
            <button type="button" className="text-sm text-zinc-300" onClick={() => setEditing(false)}>
              Cancelar
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-base font-semibold text-white">{group.group_name}</p>
            <p className="text-sm text-zinc-400">
              Mínimo {group.min_choices} · máximo {group.max_choices}
            </p>
          </div>
          <div className="flex shrink-0 gap-3">
            <button type="button" className="text-sm font-medium text-accent" onClick={beginEdit}>
              Editar
            </button>
            <button
              type="button"
              className="text-sm text-rose-400 disabled:opacity-60"
              disabled={saving}
              onClick={() => void removeGroup()}
            >
              Quitar
            </button>
          </div>
        </div>
      )}
      <ul className="space-y-1">
        {group.options.map((option) => (
          <li key={option.id} className="flex items-center justify-between text-base text-zinc-200">
            <span>{option.recipe_name}</span>
            <button
              type="button"
              className="text-sm text-rose-400"
              onClick={() => {
                void api(`/menu/options/${option.id}`, { method: "DELETE" })
                  .then(() => onChanged())
                  .catch((reason: unknown) =>
                    onError(reason instanceof Error ? reason.message : "No se pudo quitar la opción"),
                  )
              }}
            >
              Quitar
            </button>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center gap-3">
        <Select
          hideLabel
          label="Receta de la opción"
          className="min-w-56"
          selectedKeys={optionRecipe ? [optionRecipe] : []}
          onChange={(event) => onOptionRecipe(event.target.value)}
        >
          {recipes.map((recipe) => (
            <SelectItem id={recipe.id} key={recipe.id}>
              {recipe.name}
            </SelectItem>
          ))}
        </Select>
        <button
          type="button"
          className="rounded-full border border-zinc-700 px-4 py-2 text-sm text-white"
          onClick={() => {
            if (!optionRecipe) return
            void api(`/menu/groups/${group.id}/options`, {
              method: "POST",
              body: JSON.stringify({ recipe_id: optionRecipe }),
            })
              .then(() => onChanged())
              .catch((reason: unknown) =>
                onError(reason instanceof Error ? reason.message : "No se pudo agregar la opción"),
              )
          }}
        >
          Agregar opción
        </button>
      </div>
    </div>
  )
}
type Package = {
  id: string
  category_id: string
  category_name: string
  name: string
  description: string
  photo_url: string | null
  base_price_per_guest: string
  min_guests: number
  is_active: boolean
  groups: Group[]
}
type Category = { id: string; name: string }

export function PackageList() {
  const query = useQuery({ queryKey: ["packages"], queryFn: () => api<Package[]>("/menu/packages") })
  const client = useQueryClient()
  return (
    <MasterTable
      crumbs={["Dashboard", "Menú", "Paquetes"]}
      title="Paquetes"
      description="Ofertas que el cliente arma desde la micro-landing."
      rows={query.data ?? []}
      searchText={(row) => `${row.name} ${row.category_name}`}
      createTo="/menu/packages/nuevo"
      createLabel="Nuevo paquete"
      columns={[
        { key: "index", label: "#", render: () => null },
        {
          key: "photo",
          label: "Imagen",
          render: (row) => <Avatar src={row.photo_url || undefined} name={row.name} className="h-12 w-12" />,
        },
        {
          key: "name",
          label: "Nombre",
          render: (row) => (
            <div>
              <p className="text-base font-semibold text-white">{row.name}</p>
              <p className="text-sm text-zinc-400">{row.category_name}</p>
            </div>
          ),
          exportValue: (row) => row.name,
        },
        {
          key: "category",
          label: "Categoría",
          render: (row) => <Chip variant="flat">{row.category_name}</Chip>,
          exportValue: (row) => row.category_name,
        },
        {
          key: "groups",
          label: "Variantes",
          render: (row) => <span className="font-semibold text-accent">{row.groups.length}</span>,
          exportValue: (row) => String(row.groups.length),
        },
        {
          key: "price",
          label: "Precio",
          render: (row) => <span className="font-mono tabular-nums">{money(row.base_price_per_guest)}</span>,
          exportValue: (row) => row.base_price_per_guest,
        },
        {
          key: "active",
          label: "Activo",
          render: (row) => (
            <div className="flex items-center gap-2">
              <Switch
                size="sm"
                isSelected={row.is_active}
                onValueChange={(value) => {
                  void api(`/menu/packages/${row.id}`, patchBody({ is_active: value })).then(() =>
                    client.invalidateQueries({ queryKey: ["packages"] }),
                  )
                }}
              />
              <StatusPill color={row.is_active ? "success" : "warning"}>
                {row.is_active ? "Activo" : "Inactivo"}
              </StatusPill>
            </div>
          ),
        },
        {
          key: "actions",
          label: "Acciones",
          className: "text-right",
          render: (row) => (
            <RowActions
              editTo={`/menu/packages/${row.id}`}
              summary={<p>{row.name} · {money(row.base_price_per_guest)} por invitado</p>}
              onDelete={async () => {
                await api(`/menu/packages/${row.id}`, { method: "DELETE" })
                await client.invalidateQueries({ queryKey: ["packages"] })
              }}
            />
          ),
        },
      ]}
    />
  )
}

export function PackageEditor({ packageId }: { packageId: string }) {
  const isNew = packageId === "nuevo"
  const client = useQueryClient()
  const current = useQuery({
    queryKey: ["package", packageId],
    queryFn: () => api<Package>(`/menu/packages/${packageId}`),
    enabled: !isNew,
  })
  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: () => api<Category[]>("/menu/categories"),
  })
  const recipes = useQuery({
    queryKey: ["recipes"],
    queryFn: () => api<RecipeOption[]>("/menu/recipes"),
  })
  const row = current.data
  const [name, setName] = useState("")
  const [categoryId, setCategoryId] = useState("")
  const [description, setDescription] = useState("")
  const [price, setPrice] = useState("0")
  const [minGuests, setMinGuests] = useState("20")
  const [active, setActive] = useState(true)
  const [photo, setPhoto] = useState<string | null>(null)
  const [photoFile, setPhotoFile] = useState<File | null>(null)
  const [groupName, setGroupName] = useState("")
  const [groupMin, setGroupMin] = useState("1")
  const [groupMax, setGroupMax] = useState("1")
  const [optionRecipe, setOptionRecipe] = useState("")
  const [error, setError] = useState("")
  const [hydrated, setHydrated] = useState(false)
  if (row && !hydrated) {
    setName(row.name)
    setCategoryId(row.category_id)
    setDescription(row.description)
    setPrice(row.base_price_per_guest)
    setMinGuests(String(row.min_guests))
    setActive(row.is_active)
    setPhoto(row.photo_url)
    setHydrated(true)
  }

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        name,
        category_id: categoryId,
        description,
        base_price_per_guest: price,
        min_guests: Number(minGuests),
        is_active: active,
        photo_url: photo,
      }
      if (isNew) return api<Package>("/menu/packages", { method: "POST", body: JSON.stringify(body) })
      return api<Package>(`/menu/packages/${packageId}`, patchBody(body))
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["packages"] })
    },
    onError: (reason: Error) => setError(reason.message),
  })

  async function upload(file: File) {
    const body = new FormData()
    body.append("photo", file)
    try {
      const saved = await api<{ url: string }>("/menu/photos", { method: "POST", body })
      setPhoto(saved.url)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo subir la imagen")
    }
  }

  function reset() {
    setName(row?.name ?? "")
    setCategoryId(row?.category_id ?? "")
    setDescription(row?.description ?? "")
    setPrice(row?.base_price_per_guest ?? "0")
    setMinGuests(String(row?.min_guests ?? 20))
    setActive(row?.is_active ?? true)
    setPhoto(row?.photo_url ?? null)
    setPhotoFile(null)
    setGroupName("")
    setGroupMin("1")
    setGroupMax("1")
    setOptionRecipe("")
    setError("")
  }

  return (
    <SettingsShell
      icon={<PackageIcon width={22} height={22} />}
      title={isNew ? "Nuevo paquete" : "Editar paquete"}
      description="Foto, precio y publicación de la oferta en la micro-landing."
      onReset={reset}
    >
      <FormSection
        title="Imagen del paquete"
        description="La foto se muestra en la micro-landing y en el listado de paquetes."
      >
        <LogoDropZone
          presentation="inline"
          file={photoFile}
          previewUrl={photo}
          inputId="package-photo"
          heading="Foto del paquete"
          onFile={(next) => {
            setPhotoFile(next)
            if (!next) {
              setPhoto(row?.photo_url ?? null)
              return
            }
            void upload(next)
          }}
        />
      </FormSection>
      <FormSection
        title="Información comercial"
        description="Nombre, categoría y el texto que lee el cliente antes de pedir fecha."
      >
        <FormRow label="Nombre del paquete">
          <Input hideLabel label="Nombre del paquete" value={name} onValueChange={setName} />
        </FormRow>
        <FormRow label="Categoría">
          <Select
            hideLabel
            label="Categoría"
            selectedKeys={categoryId ? [categoryId] : []}
            onChange={(event) => setCategoryId(event.target.value)}
          >
            {(categories.data ?? []).map((item) => (
              <SelectItem id={item.id} key={item.id}>
                {item.name}
              </SelectItem>
            ))}
          </Select>
        </FormRow>
        <FormRow label="Descripción">
          <Textarea hideLabel label="Descripción comercial" value={description} onValueChange={setDescription} />
        </FormRow>
      </FormSection>
      <FormSection
        title="Precios y capacidad"
        description="El precio es por invitado. El mínimo evita cotizaciones por debajo de la operación."
      >
        <FormRow label="Precio por invitado">
          <Input hideLabel label="Precio por invitado" value={price} onValueChange={setPrice} />
        </FormRow>
        <FormRow label="Mínimo de invitados">
          <Input hideLabel label="Mínimo de invitados" type="number" value={minGuests} onValueChange={setMinGuests} />
        </FormRow>
      </FormSection>
      <FormSection
        title="Publicación"
        description="Un paquete inactivo deja de aparecer en la micro-landing."
      >
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
      {!isNew ? (
        <FormSection
          title="Variantes"
          description="Grupos de recetas que el cliente elige al armar el evento."
        >
          {(row?.groups ?? []).map((group) => (
            <VariantGroupCard
              key={group.id}
              group={group}
              recipes={recipes.data ?? []}
              optionRecipe={optionRecipe}
              onOptionRecipe={setOptionRecipe}
              onChanged={() => current.refetch()}
              onError={setError}
            />
          ))}
          <FormRow label="Nuevo grupo">
            <Input hideLabel label="Nuevo grupo" value={groupName} onValueChange={setGroupName} />
          </FormRow>
          <FormRow label="Mínimo">
            <Input hideLabel label="Mínimo" type="number" value={groupMin} onValueChange={setGroupMin} />
          </FormRow>
          <FormRow label="Máximo">
            <Input hideLabel label="Máximo" type="number" value={groupMax} onValueChange={setGroupMax} />
          </FormRow>
          <button
            type="button"
            className="rounded-full bg-accent px-6 py-2 text-base font-semibold text-accent-foreground"
            onClick={() => {
              void api(`/menu/packages/${packageId}/groups`, {
                method: "POST",
                body: JSON.stringify({
                  group_name: groupName,
                  min_choices: Number(groupMin),
                  max_choices: Number(groupMax),
                  is_fixed: false,
                }),
              }).then(() => current.refetch())
            }}
          >
            Agregar grupo
          </button>
        </FormSection>
      ) : null}
      {error ? <p className="py-4 text-sm text-rose-400">{error}</p> : null}
      <FormActions onSave={() => save.mutateAsync()} cancelTo="/menu/packages" saving={save.isPending} />
    </SettingsShell>
  )
}
