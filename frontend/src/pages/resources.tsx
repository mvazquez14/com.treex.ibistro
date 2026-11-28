import { Car as Truck, Factory as Store, Mug as CookingPot, Boxes3 as WarehouseIcon } from "@gravity-ui/icons"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"

import { api, money, patchBody } from "@/api"
import { RowActions } from "@/components/master/RowActions"
import { DataTableCard as MasterTable, SettingsActions as FormActions, SettingsField as FormRow, SettingsSection as FormSection, SettingsSectionForm as SettingsShell, StatusPill } from "@/components/ui-kit"
import { Button, Card, CardBody, Input, Select, SelectItem, Switch, Textarea } from "@/ui/controls"

type Named = { id: string; name: string }
type Warehouse = Named & { is_primary: boolean; location_notes: string | null }
type Ingredient = Named & {
  unit: string
  purchase_price: string
  waste_factor: number
  cooking_yield_factor: number
  supplier_id: string | null
  supplier_name: string | null
  min_stock: number
  max_stock: number
}
type Supplier = Named & { contact_name: string; phone: string; email: string | null; notes: string | null }
type StockRow = {
  warehouse_id: string
  warehouse_name: string
  ingredient_id: string
  physical_stock: number
  committed_stock: number
  available_stock: number
}
type StockLevel = { physical: number; committed: number; available: number }
type Asset = Named & {
  category: string
  total_stock: number
  rental_price_per_unit: string
  replacement_cost: string
}

const UNITS = ["kg", "lt", "pz", "gr", "ml"]
const EQUIPMENT = ["Manteleria", "Mobiliario", "Loza", "Calentamiento", "Cristaleria"]

function netUnitCost(price: string, waste: number, yieldFactor: number): number {
  const denominator = yieldFactor * (1 - waste)
  const amount = Number(price)
  if (!Number.isFinite(amount) || denominator <= 0) return amount || 0
  return amount / denominator
}
type Rule = { id: string; package_name: string; asset_name: string; guests_per_unit: number }
type Package = { id: string; name: string; groups: { id: string; group_name: string; options: unknown[] }[] }
type Category = Named & { slug: string }
type Movement = { id: string; ingredient_name: string; movement_type: string; quantity: number; created_at: string }

export function CategoryList() {
  const query = useQuery({ queryKey: ["categories"], queryFn: () => api<Category[]>("/menu/categories") })
  return (
    <MasterTable
      crumbs={["Dashboard", "Menú", "Categorías"]}
      title="Categorías"
      rows={query.data ?? []}
      searchText={(row) => row.name}
      columns={[
        { key: "index", label: "#", render: () => null },
        { key: "name", label: "Nombre", render: (row) => row.name, exportValue: (row) => row.name },
        { key: "slug", label: "Slug", render: (row) => row.slug, exportValue: (row) => row.slug },
      ]}
    />
  )
}

export function GroupList() {
  const query = useQuery({ queryKey: ["packages"], queryFn: () => api<Package[]>("/menu/packages") })
  const rows = (query.data ?? []).flatMap((item) =>
    item.groups.map((group) => ({
      id: group.id,
      name: group.group_name,
      packageName: item.name,
      packageId: item.id,
      options: group.options.length,
    })),
  )
  return (
    <MasterTable
      crumbs={["Dashboard", "Menú", "Grupos de variantes"]}
      title="Grupos de variantes"
      rows={rows}
      searchText={(row) => `${row.name} ${row.packageName}`}
      columns={[
        { key: "index", label: "#", render: () => null },
        { key: "name", label: "Grupo", render: (row) => row.name, exportValue: (row) => row.name },
        { key: "package", label: "Paquete", render: (row) => row.packageName, exportValue: (row) => row.packageName },
        {
          key: "options",
          label: "Opciones",
          render: (row) => <span className="text-accent">{row.options}</span>,
          exportValue: (row) => String(row.options),
        },
        {
          key: "actions",
          label: "Acciones",
          render: (row) => (
            <RowActions
              editTo={`/menu/packages/${row.packageId}`}
              summary={<p>{row.name} pertenece a {row.packageName}</p>}
              onDelete={async () => {
                await api(`/menu/groups/${row.id}`, { method: "DELETE" })
                await query.refetch()
              }}
            />
          ),
        },
      ]}
    />
  )
}

export function WarehouseList() {
  const query = useQuery({ queryKey: ["warehouses"], queryFn: () => api<Warehouse[]>("/warehouses") })
  const kardex = useQuery({ queryKey: ["kardex"], queryFn: () => api<Movement[]>("/warehouses/kardex") })
  const client = useQueryClient()
  return (
    <div className="mx-auto w-full max-w-7xl space-y-6 px-4 py-8 sm:px-6 lg:px-8">
      <MasterTable
        boxed={false}
        crumbs={["Dashboard", "Recursos", "Almacenes"]}
        title="Almacenes"
        description="Ubicaciones donde se guarda el inventario y se registra el kardex."
        rows={query.data ?? []}
        searchText={(row) => `${row.name} ${row.location_notes ?? ""}`}
        createTo="/warehouses/nuevo"
        createLabel="Nuevo almacén"
        columns={[
          { key: "index", label: "#", render: () => null },
          {
            key: "name",
            label: "Almacén",
            render: (row) => (
              <div>
                <p className="text-base font-semibold text-white">{row.name}</p>
                <p className="text-sm text-zinc-400">{row.location_notes || "Sin notas de ubicación"}</p>
              </div>
            ),
            exportValue: (row) => row.name,
          },
          {
            key: "primary",
            label: "Estado",
            render: (row) => (
              <StatusPill color={row.is_primary ? "success" : "default"}>
                {row.is_primary ? "Principal" : "Secundario"}
              </StatusPill>
            ),
            exportValue: (row) => (row.is_primary ? "Principal" : "Secundario"),
          },
          {
            key: "actions",
            label: "Acciones",
            className: "text-right",
            render: (row) => (
              <RowActions
                editTo={`/warehouses/${row.id}`}
                summary={<p>{row.name}</p>}
                onDelete={async () => {
                  await api(`/warehouses/${row.id}`, { method: "DELETE" })
                  await client.invalidateQueries({ queryKey: ["warehouses"] })
                }}
              />
            ),
          },
        ]}
      />
      <Card className="rounded-2xl border border-zinc-800 bg-zinc-900/90">
        <CardBody>
          <h2 className="text-lg font-semibold text-white">Kardex</h2>
          <p className="text-sm text-zinc-400">Últimos movimientos de inventario.</p>
          <ul>
            {(kardex.data ?? []).slice(0, 20).map((row) => (
              <li key={row.id} className="border-b border-zinc-800/60 py-4 text-base">
                <span className="font-semibold text-white">{row.ingredient_name}</span>
                <span className="mt-1 block text-sm text-zinc-400">
                  {row.created_at} · {row.movement_type} · <span className="tabular-nums">{row.quantity}</span>
                </span>
              </li>
            ))}
          </ul>
        </CardBody>
      </Card>
    </div>
  )
}

export function WarehouseEditor({ warehouseId }: { warehouseId: string }) {
  const isNew = warehouseId === "nuevo"
  const client = useQueryClient()
  const current = useQuery({
    queryKey: ["warehouses", warehouseId],
    queryFn: () => api<Warehouse[]>("/warehouses").then((rows) => rows.find((row) => row.id === warehouseId)),
    enabled: !isNew,
  })
  const [name, setName] = useState("")
  const [notes, setNotes] = useState("")
  const [primary, setPrimary] = useState(false)
  useEffect(() => {
    if (!current.data) return
    setName(current.data.name)
    setNotes(current.data.location_notes ?? "")
    setPrimary(current.data.is_primary)
  }, [current.data])

  function reset() {
    setName(current.data?.name ?? "")
    setNotes(current.data?.location_notes ?? "")
    setPrimary(current.data?.is_primary ?? false)
  }

  const save = useMutation({
    mutationFn: async () => {
      const body = { name, location_notes: notes, is_primary: primary }
      if (isNew) return api<Warehouse>("/warehouses", { method: "POST", body: JSON.stringify(body) })
      return api<Warehouse>(`/warehouses/${warehouseId}`, patchBody(body))
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["warehouses"] })
    },
  })

  return (
    <SettingsShell
      icon={<WarehouseIcon width={22} height={22} />}
      title={isNew ? "Nuevo almacén" : "Editar almacén"}
      description="Nombre, ubicación y si este almacén es el principal de la operación."
      onReset={reset}
    >
      <FormSection title="Datos del almacén" description="El almacén principal recibe las compras cuando no se elige otro.">
        <FormRow label="Nombre">
          <Input hideLabel label="Nombre" value={name} onValueChange={setName} />
        </FormRow>
        <FormRow label="Ubicación">
          <Textarea hideLabel label="Notas de ubicación" value={notes} onValueChange={setNotes} />
        </FormRow>
        <FormRow label="Principal">
          <div className="flex items-center gap-3">
            <Switch isSelected={primary} onValueChange={setPrimary}>
              Usar como almacén principal
            </Switch>
            <StatusPill color={primary ? "success" : "default"}>
              {primary ? "Principal" : "Secundario"}
            </StatusPill>
          </div>
        </FormRow>
      </FormSection>
      <FormActions onSave={() => save.mutateAsync()} cancelTo="/warehouses" saving={save.isPending} />
    </SettingsShell>
  )
}

function stockLevel(rows: StockRow[], ingredientId: string, warehouseId: string | null): StockLevel {
  const row = warehouseId
    ? rows.find((item) => item.ingredient_id === ingredientId && item.warehouse_id === warehouseId)
    : undefined
  return {
    physical: row?.physical_stock ?? 0,
    committed: row?.committed_stock ?? 0,
    available: row?.available_stock ?? 0,
  }
}

function StockCell({
  ingredient,
  level,
  warehouseId,
  warehouseName,
}: {
  ingredient: Ingredient
  level: StockLevel
  warehouseId: string | null
  warehouseName: string | null
}) {
  const client = useQueryClient()
  const [draft, setDraft] = useState(String(level.physical))
  const [error, setError] = useState("")
  useEffect(() => {
    setDraft(String(level.physical))
  }, [level.physical, warehouseId])
  const save = useMutation({
    mutationFn: async () => {
      if (!warehouseId) throw new Error("Configura un almacén principal en Almacenes.")
      const desired = Number(draft)
      if (!Number.isFinite(desired) || desired < 0) throw new Error("La existencia no es válida")
      if (desired < level.committed) throw new Error("La existencia no puede quedar debajo de lo apartado.")
      const delta = desired - level.physical
      if (Math.abs(delta) < 1e-9) return
      await api("/warehouses/movements", {
        method: "POST",
        body: JSON.stringify({
          warehouse_id: warehouseId,
          ingredient_id: ingredient.id,
          movement_type: "ADJUSTMENT",
          quantity: delta,
        }),
      })
    },
    onSuccess: async () => {
      setError("")
      await client.invalidateQueries({ queryKey: ["stock"] })
      await client.invalidateQueries({ queryKey: ["kardex"] })
    },
    onError: (reason: Error) => setError(reason.message),
  })
  const reorder = level.available <= ingredient.min_stock
  return (
    <div className="space-y-2">
      <StatusPill color={level.available <= 0 ? "danger" : reorder ? "warning" : "success"}>
        {reorder ? "Reordenar" : "En stock"}
      </StatusPill>
      <p className="text-sm tabular-nums text-zinc-400">
        Apartado {level.committed} {ingredient.unit}
      </p>
      <p className="text-sm tabular-nums text-zinc-200">
        Disponible {level.available} {ingredient.unit}
      </p>
      <div className="flex flex-wrap items-end gap-2">
        <Input
          label="Existencia física"
          type="number"
          min={0}
          value={draft}
          onValueChange={setDraft}
          className="w-24"
        />
        <Button variant="flat" size="sm" onPress={() => save.mutate()} isLoading={save.isPending}>
          Actualizar
        </Button>
      </div>
      <p className="text-sm text-zinc-400">
        {warehouseName ?? "Sin almacén principal"} · mín. {ingredient.min_stock}
      </p>
      {error ? <p className="text-sm text-rose-400">{error}</p> : null}
    </div>
  )
}

export function IngredientList() {
  const query = useQuery({ queryKey: ["ingredients"], queryFn: () => api<Ingredient[]>("/warehouses/ingredients") })
  const stock = useQuery({ queryKey: ["stock"], queryFn: () => api<StockRow[]>("/warehouses/stock") })
  const warehouses = useQuery({ queryKey: ["warehouses"], queryFn: () => api<Warehouse[]>("/warehouses") })
  const [warehouseId, setWarehouseId] = useState("")
  const [unit, setUnit] = useState("")
  const client = useQueryClient()
  const targetWarehouse = warehouseId
    ? (warehouses.data ?? []).find((item) => item.id === warehouseId) ?? null
    : (warehouses.data ?? []).find((item) => item.is_primary) ?? null
  const rows = (query.data ?? []).filter((row) => !unit || row.unit === unit)
  return (
    <MasterTable
      crumbs={["Dashboard", "Recursos", "Insumos"]}
      title="Insumos"
      description="Costo de compra, merma y existencia contra el mínimo de cada insumo."
      rows={rows}
      searchText={(row) => `${row.name} ${row.supplier_name ?? ""} ${row.unit}`}
      createTo="/ingredients/nuevo"
      createLabel="Nuevo insumo"
      extra={
        <>
          <Select
            ariaLabel="Almacén"
            hideLabel
            label="Almacén"
            selectedKeys={[warehouseId || "todos"]}
            onChange={(event) => setWarehouseId(event.target.value === "todos" ? "" : event.target.value)}
            className="w-full sm:w-52"
          >
            <SelectItem id="todos">Todos los almacenes</SelectItem>
            {(warehouses.data ?? []).map((item) => (
              <SelectItem id={item.id} key={item.id}>
                {item.name}
              </SelectItem>
            ))}
          </Select>
          <Select
            ariaLabel="Unidad"
            hideLabel
            label="Unidad"
            selectedKeys={[unit || "todas"]}
            onChange={(event) => setUnit(event.target.value === "todas" ? "" : event.target.value)}
            className="w-full sm:w-40"
          >
            <SelectItem id="todas">Todas las unidades</SelectItem>
            {UNITS.map((item) => (
              <SelectItem id={item} key={item}>
                {item}
              </SelectItem>
            ))}
          </Select>
        </>
      }
      columns={[
        { key: "index", label: "#", render: () => null },
        {
          key: "name",
          label: "Insumo",
          render: (row) => (
            <div>
              <p className="text-base font-semibold text-white">{row.name}</p>
              <p className="text-sm text-zinc-400">{row.unit}</p>
            </div>
          ),
          exportValue: (row) => row.name,
        },
        {
          key: "supplier",
          label: "Proveedor",
          render: (row) => row.supplier_name || "Sin proveedor",
          exportValue: (row) => row.supplier_name ?? "",
        },
        {
          key: "price",
          label: "Costo compra",
          render: (row) => <span className="tabular-nums">{money(row.purchase_price)}</span>,
          exportValue: (row) => row.purchase_price,
        },
        {
          key: "waste",
          label: "% Merma",
          render: (row) => <span className="tabular-nums">{Math.round(row.waste_factor * 100)}%</span>,
          exportValue: (row) => String(row.waste_factor),
        },
        {
          key: "net",
          label: "Costo neto",
          render: (row) => (
            <span className="tabular-nums">{money(netUnitCost(row.purchase_price, row.waste_factor, row.cooking_yield_factor))}</span>
          ),
          exportValue: (row) => String(netUnitCost(row.purchase_price, row.waste_factor, row.cooking_yield_factor)),
        },
        {
          key: "status",
          label: "Stock",
          render: (row) => (
            <StockCell
              ingredient={row}
              level={stockLevel(stock.data ?? [], row.id, targetWarehouse?.id ?? null)}
              warehouseId={targetWarehouse?.id ?? null}
              warehouseName={targetWarehouse?.name ?? null}
            />
          ),
          exportValue: (row) => String(stockLevel(stock.data ?? [], row.id, targetWarehouse?.id ?? null).available),
        },
        {
          key: "actions",
          label: "Acciones",
          className: "text-right",
          render: (row) => (
            <RowActions
              editTo={`/ingredients/${row.id}`}
              summary={<p>{row.name}</p>}
              onDelete={async () => {
                await api(`/warehouses/ingredients/${row.id}`, { method: "DELETE" })
                await client.invalidateQueries({ queryKey: ["ingredients"] })
              }}
            />
          ),
        },
      ]}
    />
  )
}

export function IngredientEditor({ ingredientId }: { ingredientId: string }) {
  const isNew = ingredientId === "nuevo"
  const client = useQueryClient()
  const current = useQuery({
    queryKey: ["ingredients", ingredientId],
    queryFn: () => api<Ingredient[]>("/warehouses/ingredients").then((rows) => rows.find((row) => row.id === ingredientId)),
    enabled: !isNew,
  })
  const suppliers = useQuery({ queryKey: ["suppliers"], queryFn: () => api<Supplier[]>("/warehouses/suppliers") })
  const [name, setName] = useState("")
  const [unit, setUnit] = useState("kg")
  const [price, setPrice] = useState("0")
  const [waste, setWaste] = useState("0")
  const [yieldFactor, setYieldFactor] = useState("1")
  const [minStock, setMinStock] = useState("0")
  const [maxStock, setMaxStock] = useState("0")
  const [supplierId, setSupplierId] = useState("")
  const [error, setError] = useState("")
  useEffect(() => {
    if (!current.data) return
    setName(current.data.name)
    setUnit(current.data.unit)
    setPrice(current.data.purchase_price)
    setWaste(String(current.data.waste_factor))
    setYieldFactor(String(current.data.cooking_yield_factor))
    setMinStock(String(current.data.min_stock))
    setMaxStock(String(current.data.max_stock))
    setSupplierId(current.data.supplier_id ?? "")
  }, [current.data])

  function reset() {
    setName(current.data?.name ?? "")
    setUnit(current.data?.unit ?? "kg")
    setPrice(current.data?.purchase_price ?? "0")
    setWaste(String(current.data?.waste_factor ?? 0))
    setYieldFactor(String(current.data?.cooking_yield_factor ?? 1))
    setMinStock(String(current.data?.min_stock ?? 0))
    setMaxStock(String(current.data?.max_stock ?? 0))
    setSupplierId(current.data?.supplier_id ?? "")
    setError("")
  }

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        name,
        unit,
        purchase_price: price,
        waste_factor: Number(waste),
        cooking_yield_factor: Number(yieldFactor),
        min_stock: Number(minStock),
        max_stock: Number(maxStock),
        supplier_id: supplierId || null,
        clear_supplier: supplierId === "",
      }
      if (isNew) return api<Ingredient>("/warehouses/ingredients", { method: "POST", body: JSON.stringify(body) })
      return api<Ingredient>(`/warehouses/ingredients/${ingredientId}`, patchBody(body))
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["ingredients"] })
    },
    onError: (reason: Error) => setError(reason.message),
  })
  const net = netUnitCost(price, Number(waste), Number(yieldFactor))
  return (
    <SettingsShell
      icon={<CookingPot width={22} height={22} />}
      title={isNew ? "Nuevo insumo" : "Editar insumo"}
      description="Unidad, costo, merma y el mínimo que dispara la reorden."
      onReset={reset}
    >
      <FormSection title="Datos del insumo" description="Nombre, unidad de compra y el proveedor habitual.">
        <FormRow label="Nombre">
          <Input hideLabel label="Nombre" value={name} onValueChange={setName} />
        </FormRow>
        <FormRow label="Unidad">
          <Select hideLabel label="Unidad" selectedKeys={[unit]} onChange={(event) => setUnit(event.target.value)}>
            {UNITS.map((item) => (
              <SelectItem id={item} key={item}>
                {item}
              </SelectItem>
            ))}
          </Select>
        </FormRow>
        <FormRow label="Proveedor">
          <Select
            hideLabel
            label="Proveedor"
            selectedKeys={supplierId ? [supplierId] : []}
            onChange={(event) => setSupplierId(event.target.value === "ninguno" ? "" : event.target.value)}
          >
            <SelectItem id="ninguno">Sin proveedor</SelectItem>
            {(suppliers.data ?? []).map((item) => (
              <SelectItem id={item.id} key={item.id}>
                {item.name}
              </SelectItem>
            ))}
          </Select>
        </FormRow>
      </FormSection>
      <FormSection
        title="Costos y merma"
        description="La merma es una fracción entre 0 y 0.95. El costo neto ya descuenta merma y rendimiento."
      >
        <FormRow label="Precio de compra">
          <Input hideLabel label="Precio de compra" value={price} onValueChange={setPrice} />
        </FormRow>
        <FormRow label="Merma">
          <Input hideLabel label="Merma" value={waste} onValueChange={setWaste} />
        </FormRow>
        <FormRow label="Rendimiento">
          <Input hideLabel label="Rendimiento" value={yieldFactor} onValueChange={setYieldFactor} />
        </FormRow>
        <FormRow label="Costo neto">
          <p className="text-base font-semibold tabular-nums text-white">{money(net)}</p>
        </FormRow>
      </FormSection>
      <FormSection
        title="Control de inventario"
        description="Cuando la existencia disponible baja del mínimo, el listado marca el insumo para reordenar."
      >
        <FormRow label="Stock mínimo">
          <Input hideLabel label="Stock mínimo" type="number" value={minStock} onValueChange={setMinStock} />
        </FormRow>
        <FormRow label="Stock máximo">
          <Input hideLabel label="Stock máximo" type="number" value={maxStock} onValueChange={setMaxStock} />
        </FormRow>
      </FormSection>
      {error ? <p className="text-sm text-rose-400">{error}</p> : null}
      <FormActions onSave={() => save.mutateAsync()} cancelTo="/ingredients" saving={save.isPending} />
    </SettingsShell>
  )
}

export function SupplierList() {
  const query = useQuery({ queryKey: ["suppliers"], queryFn: () => api<Supplier[]>("/warehouses/suppliers") })
  const client = useQueryClient()
  return (
    <MasterTable
      crumbs={["Dashboard", "Recursos", "Proveedores"]}
      title="Proveedores"
      description="Quién surte los insumos, cómo contactarlo y en qué condiciones entrega."
      rows={query.data ?? []}
      searchText={(row) => `${row.name} ${row.contact_name} ${row.phone}`}
      createTo="/suppliers/nuevo"
      createLabel="Nuevo proveedor"
      columns={[
        { key: "index", label: "#", render: () => null },
        {
          key: "name",
          label: "Razón social",
          render: (row) => (
            <div>
              <p className="text-base font-semibold text-white">{row.name}</p>
              <p className="text-sm text-zinc-400">{row.email || "Sin correo"}</p>
            </div>
          ),
          exportValue: (row) => row.name,
        },
        {
          key: "contact",
          label: "Contacto",
          render: (row) => (
            <div>
              <p className="text-base text-white">{row.contact_name || "Sin contacto"}</p>
              <p className="text-sm tabular-nums text-zinc-400">{row.phone || "Sin teléfono"}</p>
            </div>
          ),
          exportValue: (row) => row.phone,
        },
        {
          key: "notes",
          label: "Condiciones",
          render: (row) => <span className="text-sm text-zinc-300">{row.notes || "Sin condiciones"}</span>,
          exportValue: (row) => row.notes ?? "",
        },
        {
          key: "actions",
          label: "Acciones",
          className: "text-right",
          render: (row) => (
            <RowActions
              editTo={`/suppliers/${row.id}`}
              summary={<p>{row.name} · {row.phone}</p>}
              onDelete={async () => {
                await api(`/warehouses/suppliers/${row.id}`, { method: "DELETE" })
                await client.invalidateQueries({ queryKey: ["suppliers"] })
              }}
            />
          ),
        },
      ]}
    />
  )
}

export function SupplierEditor({ supplierId }: { supplierId: string }) {
  const isNew = supplierId === "nuevo"
  const current = useQuery({
    queryKey: ["suppliers", supplierId],
    queryFn: () => api<Supplier[]>("/warehouses/suppliers").then((rows) => rows.find((row) => row.id === supplierId)),
    enabled: !isNew,
  })
  const client = useQueryClient()
  const [name, setName] = useState("")
  const [phone, setPhone] = useState("")
  const [contact, setContact] = useState("")
  const [email, setEmail] = useState("")
  const [notes, setNotes] = useState("")
  const [error, setError] = useState("")
  useEffect(() => {
    if (!current.data) return
    setName(current.data.name)
    setPhone(current.data.phone)
    setContact(current.data.contact_name)
    setEmail(current.data.email ?? "")
    setNotes(current.data.notes ?? "")
  }, [current.data])

  function reset() {
    setName(current.data?.name ?? "")
    setPhone(current.data?.phone ?? "")
    setContact(current.data?.contact_name ?? "")
    setEmail(current.data?.email ?? "")
    setNotes(current.data?.notes ?? "")
    setError("")
  }

  const save = useMutation({
    mutationFn: async () => {
      const body = { name, phone, contact_name: contact, email: email || null, notes: notes || null }
      if (isNew) return api<Supplier>("/warehouses/suppliers", { method: "POST", body: JSON.stringify(body) })
      return api<Supplier>(`/warehouses/suppliers/${supplierId}`, patchBody(body))
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["suppliers"] })
    },
    onError: (reason: Error) => setError(reason.message),
  })
  return (
    <SettingsShell
      icon={<Truck width={22} height={22} />}
      title={isNew ? "Nuevo proveedor" : "Editar proveedor"}
      description="Razón social, contacto y las condiciones de entrega o crédito."
      onReset={reset}
    >
      <FormSection title="Información comercial" description="El nombre con el que identificas al proveedor en compras y en el insumo.">
        <FormRow label="Razón social">
          <Input hideLabel label="Razón social" value={name} onValueChange={setName} />
        </FormRow>
        <FormRow label="Correo">
          <Input hideLabel label="Correo" value={email} onValueChange={setEmail} />
        </FormRow>
      </FormSection>
      <FormSection title="Contacto y logística" description="Teléfono en formato internacional, por ejemplo +523312345678.">
        <FormRow label="Contacto">
          <Input hideLabel label="Contacto" value={contact} onValueChange={setContact} />
        </FormRow>
        <FormRow label="Teléfono">
          <Input hideLabel label="Teléfono" value={phone} onValueChange={setPhone} />
        </FormRow>
      </FormSection>
      <FormSection
        title="Condiciones de crédito"
        description="Días de entrega, plazo de pago o la nota que el equipo debe ver antes de comprar."
      >
        <FormRow label="Condiciones">
          <Textarea hideLabel label="Condiciones" value={notes} onValueChange={setNotes} />
        </FormRow>
      </FormSection>
      {error ? <p className="text-sm text-rose-400">{error}</p> : null}
      <FormActions onSave={() => save.mutateAsync()} cancelTo="/suppliers" saving={save.isPending} />
    </SettingsShell>
  )
}

export function EquipmentList() {
  const query = useQuery({ queryKey: ["assets"], queryFn: () => api<Asset[]>("/equipment/assets") })
  const client = useQueryClient()
  return (
    <MasterTable
      crumbs={["Dashboard", "Recursos", "Equipo"]}
      title="Equipo y mantelería"
      description="Mobiliario, loza, mantelería y equipo disponible para los eventos."
      rows={query.data ?? []}
      searchText={(row) => `${row.name} ${row.category}`}
      createTo="/equipment/nuevo"
      createLabel="Nuevo equipo"
      columns={[
        { key: "index", label: "#", render: () => null },
        {
          key: "name",
          label: "Artículo",
          render: (row) => (
            <div>
              <p className="text-base font-semibold text-white">{row.name}</p>
              <p className="text-sm text-zinc-400">{row.category}</p>
            </div>
          ),
          exportValue: (row) => row.name,
        },
        {
          key: "stock",
          label: "Cantidad total",
          render: (row) => <span className="tabular-nums">{row.total_stock}</span>,
          exportValue: (row) => String(row.total_stock),
        },
        {
          key: "available",
          label: "Disponible",
          render: (row) => <span className="tabular-nums">{row.total_stock}</span>,
          exportValue: (row) => String(row.total_stock),
        },
        {
          key: "rent",
          label: "Renta",
          render: (row) => <span className="tabular-nums">{money(row.rental_price_per_unit)}</span>,
          exportValue: (row) => row.rental_price_per_unit,
        },
        {
          key: "cost",
          label: "Reposición",
          render: (row) => <span className="tabular-nums">{money(row.replacement_cost)}</span>,
          exportValue: (row) => row.replacement_cost,
        },
        {
          key: "status",
          label: "Estado",
          render: (row) => (
            <StatusPill color={row.total_stock > 0 ? "success" : "danger"}>
              {row.total_stock > 0 ? "Disponible" : "Agotado"}
            </StatusPill>
          ),
          exportValue: (row) => (row.total_stock > 0 ? "Disponible" : "Agotado"),
        },
        {
          key: "actions",
          label: "Acciones",
          className: "text-right",
          render: (row) => (
            <RowActions
              editTo={`/equipment/${row.id}`}
              summary={<p>{row.name} · {row.total_stock} unidades</p>}
              onDelete={async () => {
                await api(`/equipment/assets/${row.id}`, { method: "DELETE" })
                await client.invalidateQueries({ queryKey: ["assets"] })
              }}
            />
          ),
        },
      ]}
    />
  )
}

export function EquipmentEditor({ assetId }: { assetId: string }) {
  const isNew = assetId === "nuevo"
  const current = useQuery({
    queryKey: ["assets", assetId],
    queryFn: () => api<Asset[]>("/equipment/assets").then((rows) => rows.find((row) => row.id === assetId)),
    enabled: !isNew,
  })
  const client = useQueryClient()
  const [name, setName] = useState("")
  const [category, setCategory] = useState("Manteleria")
  const [stock, setStock] = useState("0")
  const [rental, setRental] = useState("0")
  const [replacement, setReplacement] = useState("0")
  const [error, setError] = useState("")
  useEffect(() => {
    if (!current.data) return
    setName(current.data.name)
    setCategory(current.data.category)
    setStock(String(current.data.total_stock))
    setRental(current.data.rental_price_per_unit)
    setReplacement(current.data.replacement_cost)
  }, [current.data])

  function reset() {
    setName(current.data?.name ?? "")
    setCategory(current.data?.category ?? "Manteleria")
    setStock(String(current.data?.total_stock ?? 0))
    setRental(current.data?.rental_price_per_unit ?? "0")
    setReplacement(current.data?.replacement_cost ?? "0")
    setError("")
  }

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        name,
        category,
        total_stock: Number(stock),
        rental_price_per_unit: rental,
        replacement_cost: replacement,
      }
      if (isNew) return api<Asset>("/equipment/assets", { method: "POST", body: JSON.stringify(body) })
      return api<Asset>(`/equipment/assets/${assetId}`, patchBody(body))
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["assets"] })
    },
    onError: (reason: Error) => setError(reason.message),
  })
  const inService = Number(stock) > 0
  return (
    <SettingsShell
      icon={<Store width={22} height={22} />}
      title={isNew ? "Nuevo equipo" : "Editar equipo"}
      description="Artículo, existencia y los costos de renta o reposición."
      onReset={reset}
    >
      <FormSection title="Artículo" description="Mobiliario, loza, mantelería, cristalería o equipo de calentamiento.">
        <FormRow label="Nombre">
          <Input hideLabel label="Nombre" value={name} onValueChange={setName} />
        </FormRow>
        <FormRow label="Categoría">
          <Select hideLabel label="Categoría" selectedKeys={[category]} onChange={(event) => setCategory(event.target.value)}>
            {EQUIPMENT.map((item) => (
              <SelectItem id={item} key={item}>
                {item}
              </SelectItem>
            ))}
          </Select>
        </FormRow>
      </FormSection>
      <FormSection
        title="Inventario y costo"
        description="La existencia registrada es la cantidad disponible para asignar a eventos."
      >
        <FormRow label="Cantidad total">
          <Input hideLabel label="Cantidad total" type="number" value={stock} onValueChange={setStock} />
        </FormRow>
        <FormRow label="Renta por unidad">
          <Input hideLabel label="Renta por unidad" value={rental} onValueChange={setRental} />
        </FormRow>
        <FormRow label="Costo de reposición">
          <Input hideLabel label="Costo de reposición" value={replacement} onValueChange={setReplacement} />
        </FormRow>
        <FormRow label="Estado">
          <StatusPill color={inService ? "success" : "danger"}>
            {inService ? "Disponible" : "Agotado"}
          </StatusPill>
        </FormRow>
      </FormSection>
      {error ? <p className="text-sm text-rose-400">{error}</p> : null}
      <FormActions onSave={() => save.mutateAsync()} cancelTo="/equipment" saving={save.isPending} />
    </SettingsShell>
  )
}

export function RuleList() {
  const query = useQuery({ queryKey: ["rules"], queryFn: () => api<Rule[]>("/equipment/rules") })
  return (
    <MasterTable
      crumbs={["Dashboard", "Recursos", "Reglas"]}
      title="Reglas de equipo"
      rows={query.data ?? []}
      searchText={(row) => `${row.package_name} ${row.asset_name}`}
      columns={[
        { key: "index", label: "#", render: () => null },
        { key: "package", label: "Paquete", render: (row) => row.package_name, exportValue: (row) => row.package_name },
        { key: "asset", label: "Equipo", render: (row) => row.asset_name, exportValue: (row) => row.asset_name },
        { key: "ratio", label: "Invitados por unidad", render: (row) => row.guests_per_unit, exportValue: (row) => String(row.guests_per_unit) },
      ]}
    />
  )
}
