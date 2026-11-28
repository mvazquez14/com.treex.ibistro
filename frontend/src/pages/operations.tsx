import { AlertDialog, Modal, toast } from "@heroui/react"
import { Calendar, Factory as Store, FileText } from "@gravity-ui/icons"
import { FaWhatsapp } from "react-icons/fa"

import { Button, Card, CardBody, Chip, Input, Select, SelectItem, Switch, Textarea } from "@/ui/controls"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { useEffect, useState } from "react"

import { api, money, patchBody } from "@/api"
import { EditorLayout } from "@/components/master/EditorLayout"
import { DataTableCard as MasterTable, SettingsActions as FormActions, SettingsField as FormRow, SettingsSection as FormSection, SettingsSectionForm as SettingsShell } from "@/components/ui-kit"
import { RowActions } from "@/components/master/RowActions"

type Quote = {
  id: string
  status: string
  status_label: string
  lead_name: string
  package_name: string
  event_date: string
  guest_count: number
  total_amount: string
  created_at?: string
  discount_amount: string
  tax_amount: string
  subtotal: string
  apply_tax: boolean
  tax_rate: string
  reservation_id: string | null
  slot_label: string
  start_time: string
  end_time: string
  can_rebook: boolean
  venue_address: string
  variant_summary?: string
  package_id?: string
  slot_id?: string
  folio?: string
  category_name?: string
  phone?: string
  whatsapp_phone?: string
  email?: string | null
  whatsapp_url?: string
  special_requests?: string | null
  variants?: ServiceLine[]
  extras?: ServiceLine[]
  choices?: { group_id: string; recipe_id: string; quantity: number }[]
  extra_picks?: { extra_id: string; name: string; quantity: string }[]
}
type Opening = { event_date: string; slot_id: string; start_time: string }
type ServiceLine = { name: string; quantity: string }

function scheduleText(row: { start_time?: string; end_time?: string; slot_label?: string } | null | undefined) {
  if (!row?.start_time) return row?.slot_label ?? ""
  return row.end_time ? `${row.start_time}–${row.end_time}` : row.start_time
}

function isClosed(status: string | undefined) {
  return status === "COMPLETED" || status === "CANCELLED"
}

function quoteStatusColor(status: string | undefined): "warning" | "success" | "danger" | "default" {
  if (status === "APPROVED") return "success"
  if (status === "REJECTED") return "danger"
  if (status === "PENDING_REVIEW" || status === "SENT_TO_CLIENT" || status === "NEGOTIATING") return "warning"
  return "default"
}

function SchedulePicker({
  open,
  onClose,
  onPick,
  ignoreId,
}: {
  open: boolean
  onClose: () => void
  onPick: (choice: Opening) => void
  ignoreId?: string
}) {
  const [day, setDay] = useState("")
  const [slot, setSlot] = useState("")
  const openings = useQuery({
    queryKey: ["openings", day, ignoreId ?? ""],
    enabled: open && day.length === 10,
    queryFn: () => {
      const ignore = ignoreId ? `&ignore_reservation_id=${ignoreId}` : ""
      return api<Opening[]>(`/schedule/openings?date=${day}${ignore}`)
    },
  })
  const chosen = (openings.data ?? []).find((item) => `${item.slot_id}|${item.start_time}` === slot)
  return (
    <Modal.Backdrop isOpen={open} onOpenChange={(next) => { if (!next) onClose() }}>
      <Modal.Container>
        <Modal.Dialog className="w-full max-w-3xl">
          <Modal.CloseTrigger />
          <Modal.Header>
            <Modal.Heading>Cambiar fecha y hora</Modal.Heading>
          </Modal.Header>
          <Modal.Body className="space-y-4">
            <Input label="Fecha" type="date" value={day} onValueChange={(value) => { setDay(value); setSlot("") }} />
            <div className="flex flex-wrap gap-2">
              {(openings.data ?? []).map((item) => {
                const key = `${item.slot_id}|${item.start_time}`
                return (
                  <button
                    key={key}
                    type="button"
                    className={key === slot ? "rounded-full bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground" : "rounded-full border border-zinc-700 px-4 py-2 text-sm text-white"}
                    onClick={() => setSlot(key)}
                  >
                    {item.start_time}
                  </button>
                )
              })}
              {day && openings.data && openings.data.length === 0 ? <p className="text-sm text-zinc-400">No hay horarios disponibles ese día.</p> : null}
            </div>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="light" onPress={onClose}>Cancelar</Button>
            <Button color="primary" onPress={() => { if (chosen) onPick(chosen) }}>Guardar horario</Button>
          </Modal.Footer>
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  )
}

type Receipt = { id: string; amount: string; method_label: string; is_verified: boolean }
type Reservation = {
  id: string
  customer_name: string
  customer_phone: string
  venue_address: string
  event_date: string
  slot_label: string
  start_time: string
  end_time: string
  guest_count: number
  total_amount: string
  paid_amount: string
  balance: string
  payment_status: string
  payment_label: string
  operation_label: string
  operation_status: string
  receipts: Receipt[]
  special_requests?: string | null
}
type ReservationDetail = Reservation & {
  folio: string
  email: string | null
  whatsapp_phone: string
  whatsapp_url: string
  travel_buffer_minutes: number
  package_id?: string | null
  slot_id?: string | null
  package_name: string
  variants: ServiceLine[]
  extras: ServiceLine[]
  choices?: { group_id: string; recipe_id: string; quantity: number }[]
  extra_picks?: { extra_id: string; name: string; quantity: string }[]
  change_log?: { at: string; reason: string; before: Record<string, string>; after: Record<string, string> }[]
}
type MenuCategory = { id: string; name: string }
type MenuOption = { recipe_id: string; recipe_name: string; extra_price_per_guest?: string }
type MenuGroup = {
  id: string
  group_name: string
  min_choices: number
  max_choices: number
  is_fixed: boolean
  options: MenuOption[]
}
type MenuPackage = {
  id: string
  category_id: string
  name: string
  category_name: string
  base_price_per_guest: string
  min_guests: number
  is_active: boolean
  groups: MenuGroup[]
}
type MenuExtra = {
  id: string
  name: string
  unit_price: string
  pricing_type: string
  is_active: boolean
  category_ids: string[]
}
type Reports = {
  profitability: { reservation_id: string; customer_name: string; margin: string }[]
  purchases: { ingredient_name: string; buy_qty: number }[]
  restock: { ingredient_name: string; available_qty: number }[]
  occupancy: { event_date: string; slot_label: string; events: number; capacity: number }[]
  equipment: { asset_name: string; units: number; total_stock: number }[]
  cash: { method_label: string; pos_total: string; receipt_total: string }[]
  pending: { customer_name: string; balance: string }[]
}

export function QuoteList() {
  const client = useQueryClient()
  const query = useQuery({ queryKey: ["quotes"], queryFn: () => api<Quote[]>("/quotes") })
  const [detailId, setDetailId] = useState<string | null>(null)
  const approve = useMutation({
    mutationFn: (quoteId: string) => api<Quote>(`/quotes/${quoteId}/approve`, { method: "POST" }),
    onSuccess: async () => {
      toast.success("Cotización aprobada", { description: "El estado quedó como aprobada.", timeout: 4000 })
      await client.invalidateQueries({ queryKey: ["quotes"] })
    },
    onError: (reason: Error) => toast.danger("No se pudo aprobar", { description: reason.message, timeout: 4000 }),
  })
  return (
    <>
    <MasterTable
      crumbs={["Dashboard", "Operación", "Cotizaciones"]}
      title="Cotizaciones"
      description="Solicitudes que llegan desde la micro-landing y su seguimiento."
      frameClassName="mx-auto w-[70%] space-y-6 px-4 py-8 sm:px-6"
      rows={query.data ?? []}
      searchText={(row) => `${row.lead_name} ${row.package_name}`}
      columns={[
        { key: "index", label: "#", render: () => null },
        {
          key: "name",
          label: "Cliente",
          render: (row) => (
            <div>
              <p className="text-base font-semibold text-white">{row.lead_name}</p>
              <p className="text-sm text-zinc-400">
                {row.package_name} · {row.event_date} · {scheduleText(row)} · {row.guest_count} invitados
              </p>
            </div>
          ),
          exportValue: (row) => row.lead_name,
        },
        { key: "package", label: "Paquete", render: (row) => row.package_name, exportValue: (row) => row.package_name },
        {
          key: "status",
          label: "Estado",
          render: (row) => (
            <Chip
              size="sm"
              variant="soft"
              color={row.status === "APPROVED" ? "success" : row.status === "PENDING_REVIEW" ? "warning" : "default"}
            >
              {row.status_label}
            </Chip>
          ),
          exportValue: (row) => row.status_label,
        },
        {
          key: "total",
          label: "Total",
          render: (row) => <span className="font-mono tabular-nums">{money(row.total_amount)}</span>,
          exportValue: (row) => row.total_amount,
        },
        {
          key: "actions",
          label: "Acciones",
          className: "text-right",
          render: (row) => (
            <RowActions
              editTo={`/quotes/${row.id}`}
              onView={() => setDetailId(row.id)}
              onApprove={row.status === "APPROVED" || row.status === "REJECTED" ? undefined : () => approve.mutate(row.id)}
              summary={<p>{row.lead_name} · {row.event_date} · {money(row.total_amount)}</p>}
              onDelete={async () => undefined}
            />
          ),
        },
      ]}
    />
    <QuoteDetailDialog quoteId={detailId} onClose={() => setDetailId(null)} />
    </>
  )
}

function QuoteDetailDialog({ quoteId, onClose }: { quoteId: string | null; onClose: () => void }) {
  const client = useQueryClient()
  const detail = useQuery({
    queryKey: ["quote", quoteId],
    enabled: Boolean(quoteId),
    queryFn: () => api<Quote>(`/quotes/${quoteId}`),
  })
  const [scheduleOpen, setScheduleOpen] = useState(false)
  const row = detail.data
  const reservationId = row?.reservation_id ?? null
  const convert = useMutation({
    mutationFn: () => api<Quote>(`/quotes/${quoteId}/convert`, { method: "POST" }),
    onSuccess: async () => {
      toast.success("Reservación creada", { description: "La cotización ya es una reservación.", timeout: 4000 })
      await client.invalidateQueries({ queryKey: ["quote", quoteId] })
      await client.invalidateQueries({ queryKey: ["quotes"] })
      await client.invalidateQueries({ queryKey: ["reservations"] })
    },
    onError: (reason: Error) => toast.danger("No se pudo convertir", { description: reason.message, timeout: 4000 }),
  })
  const bookAgain = useMutation({
    mutationFn: (choice: Opening) =>
      api<Quote>(`/quotes/${quoteId}/convert`, { method: "POST", body: JSON.stringify(choice) }),
    onSuccess: async () => {
      setScheduleOpen(false)
      toast.success("Reservación creada", { description: "La nueva reservación quedó agendada.", timeout: 4000 })
      await client.invalidateQueries({ queryKey: ["quote", quoteId] })
      await client.invalidateQueries({ queryKey: ["quotes"] })
      await client.invalidateQueries({ queryKey: ["reservations"] })
    },
    onError: (reason: Error) => toast.danger("No se pudo crear la reservación", { description: reason.message, timeout: 4000 }),
  })
  return (
    <>
    <AlertDialog isOpen={quoteId !== null} onOpenChange={(next) => { if (!next) onClose() }}>
      <AlertDialog.Backdrop isOpen={quoteId !== null} onOpenChange={(next) => { if (!next) onClose() }} variant="blur" isDismissable isKeyboardDismissDisabled={false}>
        <AlertDialog.Container size="lg">
          <AlertDialog.Dialog className="max-h-[85vh] w-full max-w-3xl overflow-y-auto">
            <AlertDialog.CloseTrigger />
            <AlertDialog.Header>
              <AlertDialog.Icon status="accent">
                <span className="grid h-10 w-10 place-items-center rounded-xl bg-accent/12 text-accent">
                  <FileText width={22} height={22} />
                </span>
              </AlertDialog.Icon>
              <AlertDialog.Heading className="text-2xl font-bold text-white">
                {row?.folio} · {row?.lead_name}
              </AlertDialog.Heading>
              <p className="text-base text-zinc-300">{row ? `${row.event_date.slice(0, 10)} · ${scheduleText(row)}` : ""}</p>
            </AlertDialog.Header>
            <AlertDialog.Body className="space-y-5">
              <div className="flex justify-end">
                <Chip size="lg" variant="soft" color={quoteStatusColor(row?.status)}>{row?.status_label}</Chip>
              </div>
              <section className="space-y-1 text-base text-zinc-200">
                <h3 className="text-lg font-medium text-white">Cliente</h3>
                <p>{row?.lead_name}</p>
                <p>{row?.whatsapp_phone || row?.phone}</p>
                {row?.email ? <p>{row.email}</p> : null}
                <p>{row?.venue_address}</p>
                <p>{row?.guest_count} invitados</p>
              </section>
              <section className="space-y-1 text-base text-zinc-200">
                <h3 className="text-lg font-medium text-white">Servicio</h3>
                {row?.category_name ? <p>{row.category_name}</p> : null}
                <p>{row?.package_name}</p>
                {(row?.variants ?? []).map((line) => <p key={`${line.name}-${line.quantity}`}>{line.quantity}x {line.name}</p>)}
                {(row?.extras ?? []).map((line) => <p key={`extra-${line.name}`}>{line.quantity}x {line.name}</p>)}
                {row?.special_requests ? <p>Notas: {row.special_requests}</p> : null}
                <p className="tabular-nums">Total estimado {money(row?.total_amount)}</p>
              </section>
            </AlertDialog.Body>
            <AlertDialog.Footer>
              <a className="inline-flex items-center rounded-xl border border-zinc-700 px-4 py-2 text-base text-zinc-100" href={quoteId ? `/api/v1/quotes/${quoteId}/pdf` : "#"}>
                Crear PDF
              </a>
              {reservationId ? (
                <Button to="/reservations/$reservationId" params={{ reservationId }}>Ver reservación</Button>
              ) : row?.can_rebook ? (
                <Button color="primary" onPress={() => setScheduleOpen(true)}>Convertir a reservación</Button>
              ) : (
                <Button color="primary" isLoading={convert.isPending} onPress={() => convert.mutate()}>Convertir a reservación</Button>
              )}
            </AlertDialog.Footer>
          </AlertDialog.Dialog>
        </AlertDialog.Container>
      </AlertDialog.Backdrop>
    </AlertDialog>
    <SchedulePicker open={scheduleOpen} onClose={() => setScheduleOpen(false)} onPick={(choice) => bookAgain.mutate(choice)} />
    </>
  )
}

export function QuoteEditor({ quoteId }: { quoteId: string }) {
  const navigate = useNavigate()
  const query = useQuery({
    queryKey: ["quote", quoteId],
    queryFn: () => api<Quote>(`/quotes/${quoteId}`),
  })
  const packages = useQuery({ queryKey: ["packages"], queryFn: () => api<MenuPackage[]>("/menu/packages") })
  const extras = useQuery({ queryKey: ["extras"], queryFn: () => api<MenuExtra[]>("/menu/extras") })
  const row = query.data
  const [ready, setReady] = useState(false)
  const [day, setDay] = useState("")
  const [slot, setSlot] = useState("")
  const [packageId, setPackageId] = useState("")
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [guests, setGuests] = useState("1")
  const [extraQty, setExtraQty] = useState<Record<string, string>>({})
  const [total, setTotal] = useState("")
  const [totalTouched, setTotalTouched] = useState(false)
  const openings = useQuery({
    queryKey: ["openings", day, "quote", quoteId],
    enabled: day.length === 10,
    queryFn: () => api<Opening[]>(`/schedule/openings?date=${day}`),
  })
  useEffect(() => {
    if (!row || ready) return
    setDay(row.event_date.slice(0, 10))
    if (row.slot_id && row.start_time) setSlot(`${row.slot_id}|${row.start_time}`)
    setPackageId(row.package_id ?? "")
    setGuests(String(row.guest_count))
    setTotal(row.total_amount)
    const next: Record<string, number> = {}
    for (const choice of row.choices ?? []) next[choiceKey(choice.group_id, choice.recipe_id)] = choice.quantity
    setCounts(next)
    const picked: Record<string, string> = {}
    for (const item of row.extra_picks ?? []) picked[item.extra_id] = item.quantity
    setExtraQty(picked)
    setReady(true)
  }, [ready, row])
  const [slotId = "", slotStart = ""] = slot.split("|")
  const listed = (openings.data ?? []).some((item) => `${item.slot_id}|${item.start_time}` === slot)
  const hourChoices: Opening[] = !slotStart || listed
    ? (openings.data ?? [])
    : [{ event_date: day, slot_id: slotId, start_time: slotStart }, ...(openings.data ?? [])]
  const chosen = hourChoices.find((item) => `${item.slot_id}|${item.start_time}` === slot)
    ?? (slotId && slotStart ? { event_date: day, slot_id: slotId, start_time: slotStart } : undefined)
  const shownEnd = row && slot === `${row.slot_id}|${row.start_time}` ? row.end_time : ""
  const selected = (packages.data ?? []).find((item) => item.id === packageId)
  const visibleExtras = (extras.data ?? []).filter((item) => item.is_active && (item.category_ids.length === 0 || (selected && item.category_ids.includes(selected.category_id))))
  function groupCount(group: MenuGroup) {
    return group.options.reduce((sum, option) => sum + (counts[choiceKey(group.id, option.recipe_id)] ?? 0), 0)
  }
  function bump(group: MenuGroup, recipeId: string, delta: number) {
    const key = choiceKey(group.id, recipeId)
    const current = counts[key] ?? 0
    const next = current + delta
    if (next < 0 || groupCount(group) - current + next > group.max_choices) return
    setCounts((value) => ({ ...value, [key]: next }))
  }
  const save = useMutation({
    mutationFn: () => {
      if (!selected || !chosen) throw new Error("Elige una hora")
      const selectedOptions: Record<string, string[]> = {}
      for (const group of selected.groups) {
        if (group.is_fixed) continue
        const ids: string[] = []
        for (const option of group.options) {
          const quantity = counts[choiceKey(group.id, option.recipe_id)] ?? 0
          for (let index = 0; index < quantity; index += 1) ids.push(option.recipe_id)
        }
        if (ids.length > 0) selectedOptions[group.id] = ids
      }
      const extraLines = visibleExtras.flatMap((item) => {
        const quantity = Number(extraQty[item.id] || 0)
        return quantity > 0 ? [{ extra_id: item.id, quantity }] : []
      })
      return api<Quote>(`/quotes/${quoteId}`, {
        method: "PATCH",
        body: JSON.stringify({
          guest_count: Number(guests),
          package_id: selected.id,
          event_date: day,
          slot_id: chosen.slot_id,
          start_time: chosen.start_time,
          selected_options: selectedOptions,
          extras: extraLines,
          ...(totalTouched ? { manual_total: total } : {}),
        }),
      })
    },
    onSuccess: async () => {
      toast.success("Cotización actualizada", { description: "Los cambios quedaron guardados.", timeout: 4000 })
      await navigate({ to: "/quotes" })
    },
    onError: (reason: Error) => toast.danger("No se pudo guardar", { description: reason.message, timeout: 4000 }),
  })
  return (
    <EditorLayout
      crumbs={["Dashboard", "Operación", "Cotización"]}
      title={row?.lead_name ?? "Cotización"}
      main={
        <Card className="bg-[#18181B]">
          <CardBody className="gap-4">
            <Input label="Fecha" type="date" value={day} onValueChange={(value) => { setDay(value); if (value !== row?.event_date.slice(0, 10)) setSlot("") }} />
            <p className="text-base tabular-nums text-white">{slotStart ? `Horario: ${slotStart}${shownEnd ? `–${shownEnd}` : ""}` : "Sin horario"}</p>
            <div className="flex flex-wrap gap-2">
              {hourChoices.map((item) => {
                const key = `${item.slot_id}|${item.start_time}`
                return (
                  <button key={key} type="button" className={key === slot ? "rounded-full bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground" : "rounded-full border border-zinc-700 px-4 py-2 text-sm text-white"} onClick={() => setSlot(key)}>
                    {item.start_time}
                  </button>
                )
              })}
            </div>
            <div className="grid gap-2">
              {(packages.data ?? []).filter((item) => item.is_active).map((item) => (
                <button key={item.id} type="button" className={packageId === item.id ? "rounded-xl border border-accent px-4 py-3 text-left text-white" : "rounded-xl border border-zinc-800 px-4 py-3 text-left text-white"} onClick={() => setPackageId(item.id)}>
                  {item.name} · {money(item.base_price_per_guest)} por persona
                </button>
              ))}
            </div>
            {selected?.groups.filter((group) => !group.is_fixed).map((group) => (
              <fieldset key={group.id} className="space-y-2">
                <legend className="text-base text-white">{group.group_name} · {groupCount(group)} / {group.max_choices}</legend>
                {group.options.map((option) => (
                  <div key={option.recipe_id} className="flex items-center gap-2">
                    <button type="button" className="h-9 w-9 rounded-full border border-zinc-700" onClick={() => bump(group, option.recipe_id, -1)}>-</button>
                    <span className="w-6 text-center tabular-nums">{counts[choiceKey(group.id, option.recipe_id)] ?? 0}</span>
                    <button type="button" className="h-9 w-9 rounded-full border border-zinc-700" onClick={() => bump(group, option.recipe_id, 1)}>+</button>
                    <span>{option.recipe_name}</span>
                  </div>
                ))}
              </fieldset>
            ))}
            <Input label="Cantidad de personas" type="number" min={selected?.min_guests ?? 1} value={guests} onValueChange={setGuests} />
            {visibleExtras.map((item) => (
              <div key={item.id} className="flex items-center justify-between gap-3">
                <span>{item.name}</span>
                <Input label={`Cantidad de ${item.name}`} hideLabel type="number" min={0} value={extraQty[item.id] ?? ""} onValueChange={(value) => setExtraQty((current) => ({ ...current, [item.id]: value }))} className="w-24" />
              </div>
            ))}
            <Input label="Costo / Total final" value={total} onValueChange={(value) => { setTotalTouched(true); setTotal(value) }} />
            <div className="flex gap-2">
              <Button variant="bordered" onPress={() => void navigate({ to: "/quotes" })}>Cancelar</Button>
              <Button color="primary" isLoading={save.isPending} onPress={() => save.mutate()}>Guardar cambios</Button>
            </div>
          </CardBody>
        </Card>
      }
      side={<Card className="bg-[#18181B]"><CardBody>Estado: {row?.status_label}</CardBody></Card>}
    />
  )
}

export function ReservationList() {
  const query = useQuery({
    queryKey: ["reservations"],
    queryFn: () => api<{ reservations: Reservation[] }>("/reservations"),
  })
  const [detailId, setDetailId] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const detail = useQuery({
    queryKey: ["reservation", detailId],
    enabled: Boolean(detailId),
    queryFn: () => api<ReservationDetail>(`/reservations/${detailId}`),
  })
  const item = detail.data
  return (
    <>
    <MasterTable
      crumbs={["Dashboard", "Operación", "Reservaciones"]}
      title="Reservaciones"
      frameClassName="mx-auto w-[80%] space-y-6 px-4 py-8 sm:px-6"
      rows={query.data?.reservations ?? []}
      searchText={(row) => row.customer_name}
      columns={[
        { key: "index", label: "#", render: () => null },
        { key: "name", label: "Cliente", render: (row) => row.customer_name, exportValue: (row) => row.customer_name },
        {
          key: "date",
          label: "Fecha",
          render: (row) => <span className="tabular-nums">{row.event_date.slice(0, 10)} · {scheduleText(row)}</span>,
          exportValue: (row) => `${row.event_date} ${scheduleText(row)}`,
        },
        { key: "status", label: "Operación", render: (row) => row.operation_label, exportValue: (row) => row.operation_label },
        {
          key: "balance",
          label: "Saldo",
          render: (row) => <span className="font-mono tabular-nums">{money(row.balance)}</span>,
          exportValue: (row) => row.balance,
        },
        {
          key: "actions",
          label: "Acciones",
          render: (row) => (
            <RowActions
              editTo={`/reservations/${row.id}`}
              onView={() => setDetailId(row.id)}
              summary={<p>{row.customer_name} · saldo {money(row.balance)}</p>}
              onDelete={async () => {
                await api(`/reservations/${row.id}/cancel`, { method: "POST" })
                await query.refetch()
              }}
            />
          ),
        },
      ]}
    />
    <AlertDialog isOpen={detailId !== null && !editing} onOpenChange={(next) => { if (!next) { setDetailId(null); setEditing(false) } }}>
      <AlertDialog.Backdrop
        isOpen={detailId !== null && !editing}
        onOpenChange={(next) => { if (!next) { setDetailId(null); setEditing(false) } }}
        variant="blur"
        isDismissable
        isKeyboardDismissDisabled={false}
      >
        <AlertDialog.Container size="lg">
          <AlertDialog.Dialog className="max-h-[85vh] w-full max-w-3xl overflow-y-auto">
            <AlertDialog.CloseTrigger />
            <AlertDialog.Header>
              <AlertDialog.Icon status="accent" className="text-accent">
                <Calendar width={22} height={22} className="text-accent" />
              </AlertDialog.Icon>
              <AlertDialog.Heading>Reservación {item?.folio}</AlertDialog.Heading>
            </AlertDialog.Header>
            <AlertDialog.Body className="space-y-6">
              <div className="flex flex-wrap items-center justify-end gap-2">
                <Chip size="lg" variant="soft" color={item?.payment_status === "PAID_IN_FULL" ? "success" : "accent"}>
                  {item?.payment_status === "PAID_IN_FULL" ? "Pagado" : "Pendiente de pago"}
                </Chip>
                <Chip size="lg" variant="soft" color="accent">{item?.operation_label}</Chip>
              </div>
              <section className="space-y-2">
                <p className="text-base text-white">{item?.event_date.slice(0, 10)} · {scheduleText(item)} · Traslado {item?.travel_buffer_minutes ?? 0} min</p>
              </section>
              <section className="space-y-1 text-base text-zinc-200">
                <h3 className="text-lg font-medium text-white">Cliente y evento</h3>
                <p>{item?.customer_name}</p>
                <p>{item?.customer_phone}</p>
                {item?.email ? <p>{item.email}</p> : null}
                <p>{item?.venue_address}</p>
                <p>{item?.guest_count} invitados</p>
              </section>
              <section className="space-y-1 text-base text-zinc-200">
                <h3 className="text-lg font-medium text-white">Servicio</h3>
                <p>{item?.package_name}</p>
                {(item?.variants ?? []).map((line) => <p key={`${line.name}-${line.quantity}`}>{line.quantity}x {line.name}</p>)}
                {(item?.extras ?? []).map((line) => <p key={`extra-${line.name}`}>{line.quantity}x {line.name}</p>)}
                {item?.special_requests ? <p>Notas: {item.special_requests}</p> : null}
                <p className="tabular-nums">Total {money(item?.total_amount)} · Anticipo {money(item?.paid_amount)} · Saldo {money(item?.balance)}</p>
              </section>
              {(item?.change_log ?? []).length > 0 ? (
                <section className="space-y-2 text-base text-zinc-200">
                  <h3 className="text-lg font-medium text-white">Historial de cambios</h3>
                  {(item?.change_log ?? []).map((entry) => (
                    <p key={entry.at} className="text-sm text-zinc-300">
                      {entry.reason || "Cambio"} · {entry.before.guest_count} a {entry.after.guest_count} personas · {money(entry.before.total_amount)} a {money(entry.after.total_amount)}
                    </p>
                  ))}
                </section>
              ) : null}
            </AlertDialog.Body>
            <AlertDialog.Footer>
              <Button variant="light" onPress={() => setDetailId(null)}>Cerrar</Button>
              {item && !isClosed(item.operation_status) ? (
                <Button color="primary" onPress={() => setEditing(true)}>Editar reservación</Button>
              ) : null}
              {item?.whatsapp_url ? (
                <a
                  href={item.whatsapp_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 rounded-full bg-[#7AC017] px-5 py-2 text-base font-semibold text-[#060604]"
                >
                  <FaWhatsapp size={18} />
                  Enviar WhatsApp
                </a>
              ) : null}
            </AlertDialog.Footer>
          </AlertDialog.Dialog>
        </AlertDialog.Container>
      </AlertDialog.Backdrop>
    </AlertDialog>
    {editing && item ? <EditReservationDialog item={item} onClose={() => setEditing(false)} /> : null}
    </>
  )
}

function EditReservationDialog({ item, onClose }: { item: ReservationDetail; onClose: () => void }) {
  const client = useQueryClient()
  const packages = useQuery({ queryKey: ["packages"], queryFn: () => api<MenuPackage[]>("/menu/packages") })
  const extras = useQuery({ queryKey: ["extras"], queryFn: () => api<MenuExtra[]>("/menu/extras") })
  const [day, setDay] = useState(item.event_date.slice(0, 10))
  const [slot, setSlot] = useState(item.slot_id && item.start_time ? `${item.slot_id}|${item.start_time}` : "")
  const [packageId, setPackageId] = useState(item.package_id ?? "")
  const [counts, setCounts] = useState<Record<string, number>>(() => {
    const next: Record<string, number> = {}
    for (const choice of item.choices ?? []) next[choiceKey(choice.group_id, choice.recipe_id)] = choice.quantity
    return next
  })
  const [guests, setGuests] = useState(String(item.guest_count))
  const [extraQty, setExtraQty] = useState<Record<string, string>>(() => {
    const next: Record<string, string> = {}
    for (const extra of item.extra_picks ?? []) next[extra.extra_id] = extra.quantity
    return next
  })
  const [agreed, setAgreed] = useState(item.total_amount)
  const [agreedTouched, setAgreedTouched] = useState(false)
  const [reason, setReason] = useState("")
  const [notify, setNotify] = useState(false)
  const openings = useQuery({
    queryKey: ["openings", day, "reservation", item.id],
    enabled: day.length === 10,
    queryFn: () => api<Opening[]>(`/schedule/openings?date=${day}&ignore_reservation_id=${item.id}`),
  })
  const chosen = (openings.data ?? []).find((row) => `${row.slot_id}|${row.start_time}` === slot)
  const selected = (packages.data ?? []).find((row) => row.id === packageId)
  const visibleExtras = (extras.data ?? []).filter((row) => row.is_active && (row.category_ids.length === 0 || (selected && row.category_ids.includes(selected.category_id))))
  const guestCount = Number(guests)
  const recalculated = selected && Number.isFinite(guestCount)
    ? Number(selected.base_price_per_guest) * guestCount
      + selected.groups.filter((group) => !group.is_fixed).reduce((sum, group) => sum + group.options.reduce((inner, option) => inner + Number(option.extra_price_per_guest || 0) * (counts[choiceKey(group.id, option.recipe_id)] ?? 0) * guestCount, 0), 0)
      + visibleExtras.reduce((sum, row) => {
        const quantity = Number(extraQty[row.id] || 0)
        if (quantity <= 0) return sum
        const price = Number(row.unit_price)
        return sum + (row.pricing_type === "PER_GUEST" ? price * quantity * guestCount : price * quantity)
      }, 0)
    : Number(item.total_amount)
  useEffect(() => {
    if (!agreedTouched) setAgreed(recalculated.toFixed(2))
  }, [agreedTouched, recalculated])
  function groupCount(group: MenuGroup) {
    return group.options.reduce((sum, option) => sum + (counts[choiceKey(group.id, option.recipe_id)] ?? 0), 0)
  }
  function bump(group: MenuGroup, recipeId: string, delta: number) {
    const key = choiceKey(group.id, recipeId)
    const current = counts[key] ?? 0
    const next = current + delta
    if (next < 0 || groupCount(group) - current + next > group.max_choices) return
    setCounts((value) => ({ ...value, [key]: next }))
  }
  const paid = Number(item.paid_amount)
  const nextTotal = Number(agreed)
  const nextBalance = Number.isFinite(nextTotal) ? Math.max(0, nextTotal - paid) : 0
  const save = useMutation({
    mutationFn: () => {
      if (!selected || !chosen) throw new Error("Elige una hora")
      const selectedOptions: Record<string, string[]> = {}
      for (const group of selected.groups) {
        if (group.is_fixed) continue
        const ids: string[] = []
        for (const option of group.options) {
          const quantity = counts[choiceKey(group.id, option.recipe_id)] ?? 0
          for (let index = 0; index < quantity; index += 1) ids.push(option.recipe_id)
        }
        if (ids.length > 0) selectedOptions[group.id] = ids
      }
      const extraLines = visibleExtras.flatMap((row) => {
        const quantity = Number(extraQty[row.id] || 0)
        return quantity > 0 ? [{ extra_id: row.id, quantity }] : []
      })
      return api<ReservationDetail>(`/reservations/${item.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          event_date: day,
          slot_id: chosen.slot_id,
          start_time: chosen.start_time,
          package_id: selected.id,
          guest_count: guestCount,
          selected_options: selectedOptions,
          extras: extraLines,
          manual_total: agreed,
          reason,
        }),
      })
    },
    onSuccess: async () => {
      toast.success("Reservación actualizada", { description: "El cambio quedó guardado.", timeout: 4000 })
      if (notify && item.whatsapp_phone) {
        const digits = item.whatsapp_phone.replace(/^\+/, "")
        const text = encodeURIComponent(`Hola, tu reservación cambió. Nuevo total ${money(agreed)}. Anticipo ${money(item.paid_amount)}. Saldo ${money(String(nextBalance))}.`)
        window.open(`https://wa.me/${digits}?text=${text}`, "_blank", "noopener")
      }
      await client.invalidateQueries({ queryKey: ["reservation", item.id] })
      await client.invalidateQueries({ queryKey: ["reservations"] })
      await client.invalidateQueries({ queryKey: ["quotes"] })
      onClose()
    },
    onError: (reasonError: Error) => toast.danger("No se pudo guardar", { description: reasonError.message, timeout: 4000 }),
  })
  return (
    <AlertDialog isOpen onOpenChange={(next) => { if (!next) onClose() }}>
      <AlertDialog.Backdrop isOpen variant="blur" isDismissable isKeyboardDismissDisabled={false} onOpenChange={(next) => { if (!next) onClose() }}>
        <AlertDialog.Container size="lg">
          <AlertDialog.Dialog className="max-h-[85vh] w-full max-w-6xl overflow-y-auto">
            <AlertDialog.CloseTrigger />
            <AlertDialog.Header>
              <AlertDialog.Heading>Editar reservación</AlertDialog.Heading>
            </AlertDialog.Header>
            <AlertDialog.Body>
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                <div className="space-y-6 lg:col-span-7">
                  <Input label="Fecha" type="date" value={day} onValueChange={(value) => { setDay(value); setSlot("") }} />
                  <div className="flex flex-wrap gap-2">
                    {(openings.data ?? []).map((row) => {
                      const key = `${row.slot_id}|${row.start_time}`
                      return (
                        <button key={key} type="button" className={key === slot ? "rounded-full bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground" : "rounded-full border border-zinc-700 px-4 py-2 text-sm text-white"} onClick={() => setSlot(key)}>
                          {row.start_time}
                        </button>
                      )
                    })}
                  </div>
                  {(packages.data ?? []).filter((row) => row.is_active).map((row) => (
                    <button key={row.id} type="button" className={packageId === row.id ? "block w-full rounded-xl border border-accent px-4 py-3 text-left text-white" : "block w-full rounded-xl border border-zinc-800 px-4 py-3 text-left text-white"} onClick={() => setPackageId(row.id)}>
                      {row.name}
                    </button>
                  ))}
                  {selected?.groups.filter((group) => !group.is_fixed).map((group) => (
                    <fieldset key={group.id} className="space-y-2">
                      <legend className="text-base text-white">{group.group_name} · {groupCount(group)} / {group.max_choices}</legend>
                      {group.options.map((option) => (
                        <div key={option.recipe_id} className="flex items-center gap-2">
                          <button type="button" className="h-9 w-9 rounded-full border border-zinc-700" onClick={() => bump(group, option.recipe_id, -1)}>-</button>
                          <span className="w-6 text-center tabular-nums">{counts[choiceKey(group.id, option.recipe_id)] ?? 0}</span>
                          <button type="button" className="h-9 w-9 rounded-full border border-zinc-700" onClick={() => bump(group, option.recipe_id, 1)}>+</button>
                          <span>{option.recipe_name}</span>
                        </div>
                      ))}
                    </fieldset>
                  ))}
                  <Input label="Cantidad de personas" type="number" min={1} value={guests} onValueChange={setGuests} />
                  {visibleExtras.map((row) => (
                    <div key={row.id} className="flex items-center justify-between gap-3">
                      <span>{row.name}</span>
                      <Input label={`Cantidad de ${row.name}`} hideLabel type="number" min={0} value={extraQty[row.id] ?? ""} onValueChange={(value) => setExtraQty((current) => ({ ...current, [row.id]: value }))} className="w-24" />
                    </div>
                  ))}
                  <p className="tabular-nums text-zinc-300">Total recalculado {money(recalculated.toFixed(2))}</p>
                  <Input label="Monto acordado" value={agreed} onValueChange={(value) => { setAgreedTouched(true); setAgreed(value) }} />
                  <Input label="Motivo del cambio" value={reason} onValueChange={setReason} />
                  <Switch isSelected={notify} onValueChange={setNotify}>Notificar cambios por WhatsApp al cliente</Switch>
                </div>
                <div className="lg:col-span-5">
                  <Card className="bg-background-tertiary">
                    <CardBody className="gap-2 text-base text-zinc-200">
                      <h3 className="text-lg font-medium text-white">Antes y después</h3>
                      <p>Total anterior <span className="tabular-nums">{money(item.total_amount)}</span></p>
                      <p>Nuevo total <span className="tabular-nums">{money(agreed)}</span></p>
                      <p>Anticipo pagado <span className="tabular-nums">{money(item.paid_amount)}</span></p>
                      <p>Nuevo saldo pendiente <span className="tabular-nums">{money(nextBalance.toFixed(2))}</span></p>
                      <p>{item.event_date.slice(0, 10)} {scheduleText(item)} → {day} {chosen?.start_time ?? ""}</p>
                      <p>{item.guest_count} → {guests} personas</p>
                    </CardBody>
                  </Card>
                </div>
              </div>
            </AlertDialog.Body>
            <AlertDialog.Footer>
              <Button variant="light" onPress={onClose}>Cancelar</Button>
              <Button color="primary" isLoading={save.isPending} onPress={() => save.mutate()}>Guardar cambios</Button>
            </AlertDialog.Footer>
          </AlertDialog.Dialog>
        </AlertDialog.Container>
      </AlertDialog.Backdrop>
    </AlertDialog>
  )
}

export function ReservationEditor({ reservationId }: { reservationId: string }) {
  const query = useQuery({
    queryKey: ["reservations"],
    queryFn: () => api<{ reservations: Reservation[] }>("/reservations"),
  })
  const row = query.data?.reservations.find((item) => item.id === reservationId)
  const locked = isClosed(row?.operation_status)
  const client = useQueryClient()
  const [amount, setAmount] = useState("")
  const [method, setMethod] = useState("TRANSFER")
  const [error, setError] = useState("")
  const [scheduleOpen, setScheduleOpen] = useState(false)
  const move = useMutation({
    mutationFn: (choice: Opening) =>
      api(`/reservations/${reservationId}`, { method: "PATCH", body: JSON.stringify(choice) }),
    onSuccess: async () => {
      setScheduleOpen(false)
      toast.success("Horario actualizado", {
        description: "La fecha y la hora quedaron guardadas.",
        timeout: 4000,
      })
      await client.invalidateQueries({ queryKey: ["reservations"] })
      await client.invalidateQueries({ queryKey: ["quotes"] })
    },
    onError: (reason: Error) => toast.danger("No se pudo cambiar el horario", { description: reason.message, timeout: 4000 }),
  })
  async function act(path: string) {
    setError("")
    try {
      await api(path, { method: "POST" })
      await query.refetch()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "No se pudo actualizar")
    }
  }
  return (
    <>
    <EditorLayout
      crumbs={["Dashboard", "Operación", "Reservación"]}
      title={row?.customer_name ?? "Reservación"}
      main={
        <Card className="bg-[#18181B]">
          <CardBody className="gap-3">
            <p>{row?.event_date} · {scheduleText(row)} · {row?.guest_count} invitados</p>
            {locked ? <Chip size="sm" variant="soft">Solo lectura</Chip> : null}
            <p className="font-mono tabular-nums">Pagado {money(row?.paid_amount)} · Saldo {money(row?.balance)} · {row?.payment_label}</p>
            <ul>
              {row?.receipts.map((receipt) => (
                <li key={receipt.id} className="flex justify-between border-b border-zinc-800 py-2 text-sm">
                  <span>{receipt.method_label} · {money(receipt.amount)} {receipt.is_verified ? "verificado" : "pendiente"}</span>
                  {!receipt.is_verified ? (
                    <button type="button" className="text-accent" onClick={() => void act(`/reservations/${reservationId}/receipts/${receipt.id}/verify`)}>
                      Verificar
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
            <div className="grid grid-cols-2 gap-2">
              <Input label="Abono" labelPlacement="outside" variant="bordered" value={amount} onValueChange={setAmount} />
              <Select label="Método" labelPlacement="outside" variant="bordered" selectedKeys={[method]} onChange={(event) => setMethod(event.target.value)}>
                <SelectItem id="CASH">Efectivo</SelectItem>
                <SelectItem id="TRANSFER">Transferencia</SelectItem>
                <SelectItem id="CARD">Tarjeta</SelectItem>
              </Select>
            </div>
            {error ? <p className="text-sm text-red-400">{error}</p> : null}
            {locked ? null : (
            <Button
              color="primary"
              onPress={() => {
                void api(`/reservations/${reservationId}/receipts`, {
                  method: "POST",
                  body: JSON.stringify({ amount, payment_method: method, is_verified: false }),
                })
                  .then(() => query.refetch())
                  .catch((reason: Error) => setError(reason.message))
              }}
            >
              Registrar comprobante
            </Button>
            )}
          </CardBody>
        </Card>
      }
      side={
        <Card className="bg-[#18181B]">
          <CardBody className="gap-2">
            <p>Estado: {row?.operation_label}</p>
            {locked ? <Chip size="sm" variant="soft">Solo lectura</Chip> : (
              <>
            <Button variant="bordered" onPress={() => setScheduleOpen(true)}>Cambiar fecha y hora</Button>
            <Button onPress={() => void act(`/reservations/${reservationId}/prepare`)}>Preparar</Button>
            <Button color="primary" onPress={() => void act(`/reservations/${reservationId}/close`)}>Cerrar evento</Button>
            <Button color="danger" variant="bordered" onPress={() => void act(`/reservations/${reservationId}/cancel`)}>Cancelar</Button>
              </>
            )}
          </CardBody>
        </Card>
      }
    />
    <SchedulePicker
      open={scheduleOpen}
      ignoreId={reservationId}
      onClose={() => setScheduleOpen(false)}
      onPick={(choice) => move.mutate(choice)}
    />
    </>
  )
}

function choiceKey(groupId: string, recipeId: string) {
  return `${groupId}|${recipeId}`
}

export function PosPage() {
  const client = useQueryClient()
  const categories = useQuery({ queryKey: ["categories"], queryFn: () => api<MenuCategory[]>("/menu/categories") })
  const packages = useQuery({ queryKey: ["packages"], queryFn: () => api<MenuPackage[]>("/menu/packages") })
  const extras = useQuery({ queryKey: ["extras"], queryFn: () => api<MenuExtra[]>("/menu/extras") })
  const [step, setStep] = useState(1)
  const [day, setDay] = useState("")
  const [slot, setSlot] = useState("")
  const [categoryId, setCategoryId] = useState("")
  const [packageId, setPackageId] = useState("")
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [guests, setGuests] = useState("1")
  const [extraQty, setExtraQty] = useState<Record<string, string>>({})
  const [fullName, setFullName] = useState("")
  const [phone, setPhone] = useState("")
  const [email, setEmail] = useState("")
  const [venue, setVenue] = useState("")
  const [notes, setNotes] = useState("")
  const [createdId, setCreatedId] = useState("")
  const openings = useQuery({
    queryKey: ["openings", day, "pos"],
    enabled: day.length === 10,
    queryFn: () => api<Opening[]>(`/schedule/openings?date=${day}`),
  })
  const chosen = (openings.data ?? []).find((item) => `${item.slot_id}|${item.start_time}` === slot)
  const visiblePackages = (packages.data ?? []).filter((item) => item.is_active && item.category_id === categoryId)
  const selected = (packages.data ?? []).find((item) => item.id === packageId)
  const categoryName = (categories.data ?? []).find((item) => item.id === categoryId)?.name ?? ""
  const guestCount = Number(guests)
  const visibleExtras = (extras.data ?? []).filter((item) => {
    if (!item.is_active || !categoryId) return false
    return item.category_ids.length === 0 || item.category_ids.includes(categoryId)
  })

  function groupCount(group: MenuGroup) {
    return group.options.reduce((sum, option) => sum + (counts[choiceKey(group.id, option.recipe_id)] ?? 0), 0)
  }

  function bump(group: MenuGroup, recipeId: string, delta: number) {
    const key = choiceKey(group.id, recipeId)
    const current = counts[key] ?? 0
    const next = current + delta
    if (next < 0) return
    if (groupCount(group) - current + next > group.max_choices) return
    setCounts((value) => ({ ...value, [key]: next }))
  }

  function packageReady() {
    if (!selected) return false
    if (!Number.isFinite(guestCount) || guestCount < selected.min_guests) return false
    return selected.groups.filter((group) => !group.is_fixed).every((group) => groupCount(group) >= group.min_choices)
  }

  const send = useMutation({
    mutationFn: () => {
      if (!selected || !chosen) throw new Error("Elige una hora")
      const selectedOptions: Record<string, string[]> = {}
      for (const group of selected.groups) {
        if (group.is_fixed) continue
        const ids: string[] = []
        for (const option of group.options) {
          const quantity = counts[choiceKey(group.id, option.recipe_id)] ?? 0
          for (let index = 0; index < quantity; index += 1) ids.push(option.recipe_id)
        }
        if (ids.length > 0) selectedOptions[group.id] = ids
      }
      const extraLines = visibleExtras.flatMap((item) => {
        const quantity = Number(extraQty[item.id] || 0)
        return quantity > 0 ? [{ extra_id: item.id, quantity }] : []
      })
      return api<Quote>("/quotes", {
        method: "POST",
        body: JSON.stringify({
          package_id: selected.id,
          event_date: day,
          slot_id: chosen.slot_id,
          start_time: chosen.start_time,
          guest_count: guestCount,
          full_name: fullName,
          phone,
          whatsapp_phone: phone,
          email: email.trim() || null,
          venue_address: venue,
          special_requests: notes.trim() || null,
          selected_options: selectedOptions,
          extras: extraLines,
        }),
      })
    },
    onSuccess: async (quote) => {
      setCreatedId(quote.id)
      toast.success("Cotización creada", {
        description: "La solicitud quedó en cotizaciones.",
        timeout: 4000,
      })
      await client.invalidateQueries({ queryKey: ["quotes"] })
    },
    onError: (reason: Error) => toast.danger("No se pudo crear la cotización", { description: reason.message, timeout: 4000 }),
  })

  return (
    <EditorLayout
      crumbs={["Dashboard", "Operación", "Punto de venta"]}
      title="Punto de venta"
      main={
        <Card className="bg-[#18181B]">
          <CardBody className="grid gap-4">
            {step === 1 ? (
              <>
                <h2 className="text-lg font-semibold text-white">1. Fecha y hora del evento</h2>
                <Input label="Fecha" type="date" value={day} onValueChange={(value) => { setDay(value); setSlot("") }} />
                <div className="flex flex-wrap gap-2">
                  {(openings.data ?? []).map((item) => {
                    const key = `${item.slot_id}|${item.start_time}`
                    return (
                      <button
                        key={key}
                        type="button"
                        className={key === slot ? "rounded-full bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground" : "rounded-full border border-zinc-700 px-4 py-2 text-sm text-white"}
                        onClick={() => setSlot(key)}
                      >
                        {item.start_time}
                      </button>
                    )
                  })}
                  {day.length === 10 && openings.data && openings.data.length === 0 ? <p className="text-sm text-zinc-400">No hay horarios disponibles ese día.</p> : null}
                </div>
                <Button color="primary" onPress={() => { if (chosen) setStep(2) }}>Continuar</Button>
              </>
            ) : null}
            {step === 2 ? (
              <>
                <h2 className="text-lg font-semibold text-white">2. Categoría</h2>
                <div className="grid gap-3 sm:grid-cols-2">
                  {(categories.data ?? []).map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className={categoryId === item.id ? "rounded-2xl border border-accent bg-zinc-900/80 p-5 text-left" : "rounded-2xl border border-zinc-800 bg-zinc-900/80 p-5 text-left"}
                      onClick={() => { setCategoryId(item.id); setPackageId(""); setCounts({}) }}
                    >
                      <span className="text-lg font-semibold text-white">{item.name}</span>
                    </button>
                  ))}
                </div>
                <div className="flex gap-2">
                  <Button variant="bordered" onPress={() => setStep(1)}>Atrás</Button>
                  <Button color="primary" onPress={() => { if (categoryId) setStep(3) }}>Continuar</Button>
                </div>
              </>
            ) : null}
            {step === 3 ? (
              <>
                <h2 className="text-lg font-semibold text-white">3. Paquete, variantes y extras</h2>
                {visiblePackages.map((item) => {
                  const active = packageId === item.id
                  const choices = item.groups.filter((group) => !group.is_fixed)
                  return (
                    <article key={item.id} className={active ? "rounded-2xl border border-accent p-4" : "rounded-2xl border border-zinc-800 p-4"}>
                      <p className="text-lg font-semibold text-white">{item.name}</p>
                      <p className="text-sm text-zinc-400">{item.category_name} · mínimo {item.min_guests}</p>
                      <p className="text-base text-accent">{money(item.base_price_per_guest)} por persona</p>
                      <div className="mt-4 flex justify-end">
                        <button
                          type="button"
                          className={active ? "rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground" : "rounded-xl border border-zinc-700 px-4 py-2 text-sm font-semibold text-white"}
                          onClick={() => {
                            setPackageId(item.id)
                            setGuests(String(item.min_guests))
                            setCounts({})
                          }}
                        >
                          {active ? "Seleccionado ✓" : "Seleccionar servicio"}
                        </button>
                      </div>
                      {active && choices.length > 0 ? choices.map((group) => (
                        <fieldset key={group.id} className="mt-4 space-y-2">
                          <legend className="text-base text-white">{group.group_name} — elige {group.max_choices} · Seleccionados: {groupCount(group)} / {group.max_choices}</legend>
                          {group.options.map((option) => (
                            <div key={option.recipe_id} className="flex items-center gap-2 text-base">
                              <button type="button" className="h-9 w-9 rounded-full border border-zinc-700" onClick={() => bump(group, option.recipe_id, -1)}>-</button>
                              <span className="w-6 text-center tabular-nums">{counts[choiceKey(group.id, option.recipe_id)] ?? 0}</span>
                              <button type="button" className="h-9 w-9 rounded-full border border-zinc-700" onClick={() => bump(group, option.recipe_id, 1)}>+</button>
                              <span>{option.recipe_name}</span>
                            </div>
                          ))}
                        </fieldset>
                      )) : null}
                      {active ? item.groups.filter((group) => group.is_fixed).map((group) => (
                        <p key={group.id} className="mt-3 text-sm text-zinc-300">Incluido: {group.group_name}</p>
                      )) : null}
                    </article>
                  )
                })}
                {selected ? (
                  <>
                    <Input label="Invitados" type="number" min={selected.min_guests} value={guests} onValueChange={setGuests} />
                    <h3 className="text-base font-semibold text-white">Extras</h3>
                    {visibleExtras.map((item) => (
                      <div key={item.id} className="flex items-center justify-between gap-3 rounded-xl bg-zinc-900/80 p-3">
                        <div>
                          <p className="text-base text-white">{item.name}</p>
                          <p className="text-sm text-accent">{money(item.unit_price)} {item.pricing_type === "PER_GUEST" ? "por invitado" : "por unidad"}</p>
                        </div>
                        <Input label={`Cantidad de ${item.name}`} hideLabel type="number" min={0} value={extraQty[item.id] ?? ""} onValueChange={(value) => setExtraQty((current) => ({ ...current, [item.id]: value }))} className="w-24" />
                      </div>
                    ))}
                  </>
                ) : null}
                <div className="flex gap-2">
                  <Button variant="bordered" onPress={() => setStep(2)}>Atrás</Button>
                  <Button color="primary" onPress={() => { if (packageReady()) setStep(4) }}>Continuar</Button>
                </div>
              </>
            ) : null}
            {step === 4 ? (
              <>
                <h2 className="text-lg font-semibold text-white">4. Datos y confirmación</h2>
                <div className="space-y-1 rounded-xl bg-zinc-900/80 p-4 text-base text-zinc-200">
                  <p><span className="text-zinc-400">Fecha:</span> {day}</p>
                  <p><span className="text-zinc-400">Horario:</span> {chosen?.start_time}</p>
                  <p><span className="text-zinc-400">Categoría:</span> {categoryName}</p>
                  <p><span className="text-zinc-400">Paquete:</span> {selected?.name}</p>
                  <p><span className="text-zinc-400">Invitados:</span> {guests}</p>
                </div>
                <Input label="Nombre completo" value={fullName} onValueChange={setFullName} />
                <Input label="WhatsApp / Teléfono" value={phone} onValueChange={setPhone} placeholder="+523312345678" />
                <Input label="Correo electrónico" value={email} onValueChange={setEmail} />
                <Input label="Dirección o colonia del evento" value={venue} onValueChange={setVenue} />
                <Textarea label="Notas adicionales" value={notes} onValueChange={setNotes} />
                <div className="flex flex-wrap gap-2">
                  <Button variant="bordered" onPress={() => setStep(3)}>Atrás</Button>
                  {createdId ? (
                    <Button to="/quotes/$quoteId" params={{ quoteId: createdId }}>Ver cotización</Button>
                  ) : (
                    <Button
                      color="primary"
                      isLoading={send.isPending}
                      onPress={() => {
                        if (fullName.trim() && phone.trim() && venue.trim()) send.mutate()
                      }}
                    >
                      Enviar solicitud de cotización
                    </Button>
                  )}
                </div>
              </>
            ) : null}
          </CardBody>
        </Card>
      }
      side={
        <Card className="bg-[#18181B]">
          <CardBody className="gap-2 text-base text-zinc-300">
            <h2 className="text-lg font-semibold text-white">Tu pedido</h2>
            <p>{day || "Sin fecha"}</p>
            <p>{chosen?.start_time || "Sin horario"}</p>
            <p>{categoryName || "Sin categoría"}</p>
            <p className="text-white">{selected?.name || "Sin paquete"}</p>
            <p>{guests} invitados</p>
          </CardBody>
        </Card>
      }
    />
  )
}

export function ReportsPage() {
  const query = useQuery({ queryKey: ["reports"], queryFn: () => api<Reports>("/reports") })
  const data = query.data
  return (
    <div className="mx-auto grid w-full max-w-7xl gap-6 px-4 py-8 sm:px-6 lg:px-8">
      <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">Reportes</h1>
      <Report title="Rentabilidad real" rows={(data?.profitability ?? []).map((row) => `${row.customer_name}: ${money(row.margin)}`)} />
      <Report title="Explosión de compras" rows={(data?.purchases ?? []).map((row) => `${row.ingredient_name}: ${row.buy_qty}`)} empty="Sin compras pendientes" />
      <Report title="Alertas de reabastecimiento" rows={(data?.restock ?? []).map((row) => `${row.ingredient_name}: ${row.available_qty}`)} />
      <Report title="Ocupación" rows={(data?.occupancy ?? []).map((row) => `${row.event_date} ${row.slot_label}: ${row.events}/${row.capacity}`)} />
      <Report title="Equipo" rows={(data?.equipment ?? []).map((row) => `${row.asset_name}: ${row.units}/${row.total_stock}`)} />
      <Report title="Corte de caja" rows={(data?.cash ?? []).map((row) => `${row.method_label}: POS ${money(row.pos_total)} · comprobantes ${money(row.receipt_total)}`)} />
      <Report title="Saldos pendientes" rows={(data?.pending ?? []).map((row) => `${row.customer_name}: ${money(row.balance)}`)} />
    </div>
  )
}

function Report({ title, rows, empty = "Sin datos" }: { title: string; rows: string[]; empty?: string }) {
  return (
    <Card className="bg-[#18181B]">
      <CardBody>
        <h2 className="mb-2 font-semibold">{title}</h2>
        {rows.length === 0 ? <p className="text-sm text-zinc-400">{empty}</p> : rows.map((row) => <p key={row} className="text-sm">{row}</p>)}
      </CardBody>
    </Card>
  )
}

type BusinessProfile = {
  business_name: string
  rfc: string
  slug: string
  logo_url: string | null
  address: string
  whatsapp_phone: string
  contact_phone: string
  min_guests: number
  max_guests: number
  accepts_cash: boolean
  accepts_transfer: boolean
  transfer_instructions: string
  show_prices_public: boolean
  service_duration_minutes: number
  travel_buffer_minutes: number
}

type ScheduleSlot = {
  id: string
  day_of_week: number
  start_time: string
  end_time: string
  is_active: boolean
}

const WEEKDAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

function HoursEditor() {
  const query = useQuery({
    queryKey: ["schedule-slots"],
    queryFn: () => api<ScheduleSlot[]>("/schedule/slots"),
  })
  const [rows, setRows] = useState<Record<number, { id?: string; start: string; end: string; active: boolean }>>({})
  const [ready, setReady] = useState(false)
  const [message, setMessage] = useState("")
  if (query.data && !ready) {
    const next: typeof rows = {}
    for (let day = 0; day < 7; day += 1) {
      const slot = query.data.find((item) => item.day_of_week === day)
      next[day] = {
        id: slot?.id,
        start: slot?.start_time ?? "10:00",
        end: slot?.end_time ?? "18:00",
        active: slot?.is_active ?? false,
      }
    }
    setRows(next)
    setReady(true)
  }

  async function saveDay(day: number) {
    const row = rows[day]
    if (!row) return
    setMessage("")
    const body = {
      day_of_week: day,
      start_time: row.start,
      end_time: row.end,
      is_active: row.active,
    }
    try {
      const saved = row.id
        ? await api<ScheduleSlot>(`/schedule/slots/${row.id}`, patchBody(body))
        : await api<ScheduleSlot>("/schedule/slots", { method: "POST", body: JSON.stringify(body) })
      setRows((current) => ({ ...current, [day]: { ...row, id: saved.id } }))
      setMessage("")
      toast.success("Cambios guardados", {
        description: `${WEEKDAYS[day]} se actualizó correctamente.`,
        timeout: 4000,
      })
      await query.refetch()
    } catch (reason) {
      const description = reason instanceof Error ? reason.message : "No se pudo guardar el horario"
      setMessage(description)
      toast.danger("Error al guardar", { description, timeout: 4000 })
    }
  }

  return (
    <FormSection
      title="Horarios de atención"
      description="Cada día ofrece inicios cada 30 minutos. El servicio debe terminar antes del cierre."
    >
      {WEEKDAYS.map((label, day) => {
        const row = rows[day]
        if (!row) return null
        return (
          <div key={label} className="grid items-center gap-3 border-b border-zinc-800/70 py-4 sm:grid-cols-12">
            <span className="text-sm font-medium text-zinc-200 sm:col-span-3">{label}</span>
            <div className="sm:col-span-2">
              <Input hideLabel label="Apertura" value={row.start} onValueChange={(value) => setRows((current) => ({ ...current, [day]: { ...row, start: value } }))} />
            </div>
            <div className="sm:col-span-2">
              <Input hideLabel label="Cierre" value={row.end} onValueChange={(value) => setRows((current) => ({ ...current, [day]: { ...row, end: value } }))} />
            </div>
            <div className="sm:col-span-3">
              <Switch isSelected={row.active} onValueChange={(value) => setRows((current) => ({ ...current, [day]: { ...row, active: value } }))}>
                Activo
              </Switch>
            </div>
            <button type="button" className="text-sm font-medium text-accent sm:col-span-2" onClick={() => void saveDay(day)}>
              Guardar día
            </button>
          </div>
        )
      })}
      {message ? <p className="text-sm text-zinc-300">{message}</p> : null}
    </FormSection>
  )
}

export function SettingsPage({ name, email, billing }: { name?: string; email?: string; billing?: string }) {
  const client = useQueryClient()
  const profile = useQuery({
    queryKey: ["business-profile"],
    queryFn: () => api<BusinessProfile>("/operations/profile"),
  })
  const [form, setForm] = useState<BusinessProfile | null>(null)
  const [tab, setTab] = useState<"general" | "hours">("general")
  const [error, setError] = useState("")
  if (profile.data && form === null) setForm(profile.data)

  function update<K extends keyof BusinessProfile>(key: K, value: BusinessProfile[K]) {
    setForm((current) => (current ? { ...current, [key]: value } : current))
  }

  function reset() {
    if (profile.data) setForm({ ...profile.data })
    setError("")
  }

  const save = useMutation({
    mutationFn: () => {
      if (!form) throw new Error("Sin datos del negocio")
      return api<BusinessProfile>(
        "/operations/profile",
        patchBody({
          address: form.address,
          whatsapp_phone: form.whatsapp_phone,
          contact_phone: form.contact_phone,
          min_guests: Number(form.min_guests),
          max_guests: Number(form.max_guests),
          accepts_cash: form.accepts_cash,
          accepts_transfer: form.accepts_transfer,
          transfer_instructions: form.transfer_instructions,
          show_prices_public: form.show_prices_public,
          service_duration_minutes: Number(form.service_duration_minutes),
          travel_buffer_minutes: Number(form.travel_buffer_minutes),
        }),
      )
    },
    onSuccess: async (saved) => {
      setForm(saved)
      setError("")
      await client.invalidateQueries({ queryKey: ["business-profile"] })
    },
    onError: (reason: Error) => setError(reason.message),
  })

  return (
    <SettingsShell
      icon={<Store width={22} height={22} />}
      title="Configuración del negocio"
      description="Contacto, capacidad y cobro que el cliente ve en la micro-landing."
      onReset={reset}
      action={billing ? <Button href={billing}>Facturación</Button> : null}
    >
      {profile.isError ? (
        <p className="py-8 text-base text-zinc-400">
          No se pudo cargar el perfil. Si la suscripción está inactiva, actívala en Nuna.
        </p>
      ) : null}
      <div className="flex gap-6 border-b border-zinc-800">
        <button
          type="button"
          className={`pb-3 text-base ${tab === "general" ? "border-b-2 border-accent font-semibold text-white" : "text-zinc-400"}`}
          onClick={() => setTab("general")}
        >
          General
        </button>
        <button
          type="button"
          className={`pb-3 text-base ${tab === "hours" ? "border-b-2 border-accent font-semibold text-white" : "text-zinc-400"}`}
          onClick={() => setTab("hours")}
        >
          Horarios de atención
        </button>
      </div>
      {tab === "hours" ? <HoursEditor /> : null}
      {form && tab === "general" ? (
        <>
          <FormSection
            title="Identidad"
            description="El nombre y el RFC llegan de Nuna. El correo de la cuenta no se edita aquí."
          >
            {form.logo_url ? (
              <img alt="Logo del negocio" className="size-20 rounded-2xl object-cover" src={form.logo_url} />
            ) : null}
            <FormRow label="Negocio">
              <Input hideLabel label="Negocio" value={form.business_name || name || ""} />
            </FormRow>
            <FormRow label="RFC">
              <Input hideLabel label="RFC" value={form.rfc} />
            </FormRow>
            <FormRow label="Correo">
              <Input hideLabel label="Correo" value={email || ""} />
            </FormRow>
            <FormRow label="Micro-landing">
              <Input hideLabel label="Micro-landing" value={form.slug} />
            </FormRow>
          </FormSection>
          <FormSection
            title="Contacto"
            description="Teléfonos en formato internacional, por ejemplo +523312345678."
          >
            <FormRow label="Dirección">
              <Textarea hideLabel label="Dirección" value={form.address} onValueChange={(value) => update("address", value)} />
            </FormRow>
            <FormRow label="WhatsApp">
              <Input
                hideLabel
                label="WhatsApp"
                value={form.whatsapp_phone}
                onValueChange={(value) => update("whatsapp_phone", value)}
              />
            </FormRow>
            <FormRow label="Teléfono">
              <Input
                hideLabel
                label="Teléfono"
                value={form.contact_phone}
                onValueChange={(value) => update("contact_phone", value)}
              />
            </FormRow>
          </FormSection>
          <FormSection
            title="Capacidad y cobro"
            description="Límites de invitados y las instrucciones que ve el cliente al pagar por transferencia."
          >
            <FormRow label="Mínimo de invitados">
              <Input
                hideLabel
                label="Mínimo de invitados"
                type="number"
                value={String(form.min_guests)}
                onValueChange={(value) => update("min_guests", Number(value))}
              />
            </FormRow>
            <FormRow label="Máximo de invitados">
              <Input
                hideLabel
                label="Máximo de invitados"
                type="number"
                value={String(form.max_guests)}
                onValueChange={(value) => update("max_guests", Number(value))}
              />
            </FormRow>
            <FormRow label="Efectivo">
              <Switch isSelected={form.accepts_cash} onValueChange={(value) => update("accepts_cash", value)}>
                Acepta efectivo
              </Switch>
            </FormRow>
            <FormRow label="Transferencia">
              <Switch isSelected={form.accepts_transfer} onValueChange={(value) => update("accepts_transfer", value)}>
                Acepta transferencia
              </Switch>
            </FormRow>
            <FormRow label="Instrucciones">
              <Textarea
                hideLabel
                label="Instrucciones de transferencia"
                value={form.transfer_instructions}
                onValueChange={(value) => update("transfer_instructions", value)}
              />
            </FormRow>
            <FormRow label="Duración del servicio">
              <Input
                hideLabel
                label="Duración del servicio"
                type="number"
                value={String(form.service_duration_minutes ?? 120)}
                onValueChange={(value) => update("service_duration_minutes", Number(value))}
              />
            </FormRow>
            <FormRow label="Traslado">
              <Input
                hideLabel
                label="Traslado"
                type="number"
                value={String(form.travel_buffer_minutes ?? 60)}
                onValueChange={(value) => update("travel_buffer_minutes", Number(value))}
              />
            </FormRow>
            <FormRow label="Precios públicos">
              <div className="flex items-center gap-3">
                <Switch
                  isSelected={form.show_prices_public}
                  onValueChange={(value) => update("show_prices_public", value)}
                >
                  Mostrar precios en la micro-landing
                </Switch>
                <Chip size="sm" variant="soft" color={form.show_prices_public ? "success" : "warning"}>
                  {form.show_prices_public ? "Visibles" : "Ocultos"}
                </Chip>
              </div>
            </FormRow>
          </FormSection>
          {error ? <p className="text-sm text-rose-400">{error}</p> : null}
          <FormActions onSave={() => save.mutateAsync()} cancelTo="/" saving={save.isPending} />
        </>
      ) : profile.isLoading ? (
        <p className="py-8 text-base text-zinc-400">Cargando configuración…</p>
      ) : null}
    </SettingsShell>
  )
}
