import { Cup as ChefHat } from "@gravity-ui/icons"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import { api, money, patchBody } from "@/api"
import { RowActions } from "@/components/master/RowActions"
import { DataTableCard as MasterTable, SettingsActions as FormActions, SettingsField as FormRow, SettingsSection as FormSection, SettingsSectionForm as SettingsShell, StatusPill } from "@/components/ui-kit"
import { Input, Select, SelectItem, Switch } from "@/ui/controls"

type RecipeItem = {
  id: string
  ingredient_id: string | null
  sub_recipe_id: string | null
  label: string
  unit: string | null
  net_qty_per_portion: number
  gross_qty: number | null
}
type DraftLine = { key: string; id: string | null; ingredientId: string; net: string }
type PortionPreview = { cost_per_portion: string | null; cost_note: string | null }
type Recipe = {
  id: string
  name: string
  is_sub_recipe: boolean
  portion_size: number
  portion_unit: string
  cost_per_portion: string | null
  cost_note: string | null
  items: RecipeItem[]
}
type Ingredient = {
  id: string
  name: string
  unit: string
  purchase_price: string
  waste_factor: number
  cooking_yield_factor: number
}

function grossQuantity(ingredient: Ingredient | undefined, net: number): number | null {
  if (!ingredient || !Number.isFinite(net) || net <= 0) return null
  const denominator = ingredient.cooking_yield_factor * (1 - ingredient.waste_factor)
  if (denominator <= 0) return null
  return net / denominator
}

export function RecipeList() {
  const query = useQuery({
    queryKey: ["recipes"],
    queryFn: () => api<Recipe[]>("/menu/recipes"),
  })
  const client = useQueryClient()
  const rows = query.data ?? []
  return (
    <MasterTable
      crumbs={["Dashboard", "Menú", "Recetas y Costeo"]}
      title="Recetas y Costeo"
      description="Costo por porción calculado con los ingredientes y el rendimiento."
      frameClassName="mx-auto w-[80%] space-y-6 px-4 py-8 sm:px-6"
      rows={rows}
      searchText={(row) => row.name}
      createTo="/menu/recipes/nuevo"
      createLabel="Nueva receta"
      columns={[
        { key: "index", label: "#", render: () => null, exportValue: () => "" },
        {
          key: "name",
          label: "Nombre",
          render: (row) => (
            <div>
              <p className="text-base font-semibold text-white">{row.name}</p>
              <p className="text-sm text-zinc-400">
                {row.portion_size} {row.portion_unit}
              </p>
            </div>
          ),
          exportValue: (row) => row.name,
        },
        {
          key: "portion",
          label: "Porción",
          render: (row) => `${row.portion_size} ${row.portion_unit}`,
          exportValue: (row) => `${row.portion_size} ${row.portion_unit}`,
        },
        {
          key: "items",
          label: "Insumos",
          render: (row) => <span className="font-semibold text-accent">{row.items.length}</span>,
          exportValue: (row) => String(row.items.length),
        },
        {
          key: "cost",
          label: "Costo",
          render: (row) => (
            <span className="font-mono tabular-nums">
              {row.cost_per_portion ? money(row.cost_per_portion) : "—"}
            </span>
          ),
          exportValue: (row) => row.cost_per_portion ?? "",
        },
        {
          key: "status",
          label: "Estado",
          render: (row) => (
            <StatusPill color={row.is_sub_recipe ? "warning" : "success"}>
              {row.is_sub_recipe ? "Sub-receta" : "Activa"}
            </StatusPill>
          ),
          exportValue: (row) => (row.is_sub_recipe ? "Sub-receta" : "Activa"),
        },
        {
          key: "actions",
          label: "Acciones",
          className: "text-right",
          render: (row) => (
            <RowActions
              editTo={`/menu/recipes/${row.id}`}
              summary={
                <p>
                  {row.name}: {row.items.length} líneas. {row.cost_note}
                </p>
              }
              onDelete={async () => {
                await api(`/menu/recipes/${row.id}`, { method: "DELETE" })
                await client.invalidateQueries({ queryKey: ["recipes"] })
              }}
            />
          ),
        },
      ]}
    />
  )
}

export function RecipeEditor({ recipeId }: { recipeId: string }) {
  const isNew = recipeId === "nuevo"
  const client = useQueryClient()
  const recipe = useQuery({
    queryKey: ["recipe", recipeId],
    queryFn: () => api<Recipe>(`/menu/recipes/${recipeId}`),
    enabled: !isNew,
  })
  const ingredients = useQuery({
    queryKey: ["ingredients"],
    queryFn: () => api<Ingredient[]>("/warehouses/ingredients"),
  })
  const recipes = useQuery({
    queryKey: ["recipes"],
    queryFn: () => api<Recipe[]>("/menu/recipes"),
  })
  const current = recipe.data
  const [name, setName] = useState(current?.name ?? "")
  const [portion, setPortion] = useState(String(current?.portion_size ?? 1))
  const [unit, setUnit] = useState(current?.portion_unit ?? "porción")
  const [sub, setSub] = useState(current?.is_sub_recipe ?? false)
  const [lines, setLines] = useState<DraftLine[] | null>(null)
  const [removed, setRemoved] = useState<string[]>([])

  if (current && name === "" && current.name) {
    setName(current.name)
    setPortion(String(current.portion_size))
    setUnit(current.portion_unit)
    setSub(current.is_sub_recipe)
  }
  if (current && lines === null) {
    setLines(
      current.items.map((item) => ({
        key: item.id,
        id: item.id,
        ingredientId: item.ingredient_id ?? "",
        net: String(item.net_qty_per_portion),
      })),
    )
  }

  const draft = lines ?? []
  const preview = useQuery({
    queryKey: ["recipe-preview", recipeId, draft],
    enabled: !isNew && lines !== null,
    queryFn: () =>
      api<PortionPreview>(`/menu/recipes/${recipeId}/preview`, {
        method: "POST",
        body: JSON.stringify({
          items: draft
            .filter((line) => line.ingredientId && Number(line.net) > 0)
            .map((line) => ({
              ingredient_id: line.ingredientId,
              net_qty_per_portion: Number(line.net),
            })),
        }),
      }),
  })

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        name,
        portion_size: Number(portion),
        portion_unit: unit,
        is_sub_recipe: sub,
      }
      const saved = isNew
        ? await api<Recipe>("/menu/recipes", { method: "POST", body: JSON.stringify(body) })
        : await api<Recipe>(`/menu/recipes/${recipeId}`, patchBody(body))
      if (!isNew) {
        for (const itemId of removed) {
          await api(`/menu/recipe-items/${itemId}`, { method: "DELETE" })
        }
        for (const line of draft) {
          const payload = {
            ingredient_id: line.ingredientId,
            net_qty_per_portion: Number(line.net),
          }
          if (!line.ingredientId || !(Number(line.net) > 0)) continue
          if (line.id) {
            await api(`/menu/recipe-items/${line.id}`, patchBody(payload))
          } else {
            await api(`/menu/recipes/${recipeId}/items`, {
              method: "POST",
              body: JSON.stringify(payload),
            })
          }
        }
      }
      return saved
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["recipes"] })
    },
  })

  function reset() {
    setName(current?.name ?? "")
    setPortion(String(current?.portion_size ?? 1))
    setUnit(current?.portion_unit ?? "porción")
    setSub(current?.is_sub_recipe ?? false)
    setRemoved([])
    setLines(
      (current?.items ?? []).map((item) => ({
        key: item.id,
        id: item.id,
        ingredientId: item.ingredient_id ?? "",
        net: String(item.net_qty_per_portion),
      })),
    )
  }

  function updateLine(key: string, patch: Partial<DraftLine>) {
    setLines((currentLines) =>
      (currentLines ?? []).map((line) => (line.key === key ? { ...line, ...patch } : line)),
    )
  }

  return (
    <SettingsShell
      icon={<ChefHat width={22} height={22} />}
      title={isNew ? "Nueva receta" : "Editar receta"}
      description="Nombre, porción e ingredientes que alimentan el costo del menú."
      widthClassName="w-[80%]"
      onReset={reset}
    >
      <FormSection
        title="Información de la receta"
        description="El nombre y la porción se usan en paquetes, cotizaciones y el costo por comensal."
      >
        <FormRow label="Nombre">
          <Input hideLabel label="Nombre" value={name} onValueChange={setName} />
        </FormRow>
        <FormRow label="Tamaño de porción">
          <Input hideLabel label="Tamaño de porción" type="number" value={portion} onValueChange={setPortion} />
        </FormRow>
        <FormRow label="Unidad">
          <Input hideLabel label="Unidad" value={unit} onValueChange={setUnit} />
        </FormRow>
        <FormRow label="Sub-receta">
          <Switch isSelected={sub} onValueChange={setSub}>
            Se puede usar dentro de otras recetas
          </Switch>
        </FormRow>
      </FormSection>
      {!isNew ? (
        <FormSection
          title="Ingredientes y Rendimiento"
          description="Cambia el insumo y la cantidad neta. La unidad y la cantidad bruta salen del insumo, y el costo por porción se ve antes de guardar."
        >
          <p className="text-base font-semibold tabular-nums text-accent">
            Costo por porción:{" "}
            {preview.data?.cost_per_portion
              ? money(preview.data.cost_per_portion)
              : current?.cost_per_portion
                ? money(current.cost_per_portion)
                : "sin costo"}
          </p>
          {preview.data?.cost_note || current?.cost_note ? (
            <p className="text-sm text-zinc-400">{preview.data?.cost_note || current?.cost_note}</p>
          ) : null}
          <ul className="space-y-4">
            {draft.map((line) => {
              const ingredient = (ingredients.data ?? []).find((item) => item.id === line.ingredientId)
              const gross = grossQuantity(ingredient, Number(line.net))
              return (
                <li key={line.key} className="space-y-3 border-b border-zinc-800/60 pb-4">
                  <Select
                    hideLabel
                    label="Insumo"
                    selectedKeys={line.ingredientId ? [line.ingredientId] : []}
                    onChange={(event) => updateLine(line.key, { ingredientId: event.target.value })}
                  >
                    {(ingredients.data ?? []).map((item) => (
                      <SelectItem id={item.id} key={item.id}>
                        {item.name}
                      </SelectItem>
                    ))}
                  </Select>
                  <div className="grid gap-3 sm:grid-cols-3">
                    <Input
                      hideLabel
                      label="Cantidad neta"
                      value={line.net}
                      onValueChange={(value) => updateLine(line.key, { net: value })}
                    />
                    <p className="text-base text-zinc-300">Unidad: {ingredient?.unit ?? "—"}</p>
                    <p className="text-base tabular-nums text-zinc-300">
                      Bruta: {gross === null ? "—" : gross.toLocaleString("es-MX", { maximumFractionDigits: 3 })}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="text-sm text-rose-400"
                    onClick={() => {
                      if (line.id) setRemoved((currentIds) => [...currentIds, line.id as string])
                      setLines((currentLines) => (currentLines ?? []).filter((item) => item.key !== line.key))
                    }}
                  >
                    Quitar
                  </button>
                </li>
              )
            })}
          </ul>
          <button
            type="button"
            className="rounded-full bg-accent px-6 py-2 text-base font-semibold text-accent-foreground"
            onClick={() =>
              setLines((currentLines) => [
                ...(currentLines ?? []),
                { key: `new-${Date.now()}`, id: null, ingredientId: "", net: "1" },
              ])
            }
          >
            Agregar línea
          </button>
          <p className="text-sm text-zinc-400">
            Sub-recetas disponibles: {(recipes.data ?? []).filter((row) => row.is_sub_recipe).length}
          </p>
        </FormSection>
      ) : null}
      <FormActions onSave={() => save.mutateAsync()} cancelTo="/menu/recipes" saving={save.isPending} />
    </SettingsShell>
  )
}
