import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { useMemo, useState } from "react"

import { api, money } from "@/api"

type Reservation = {
  id: string
  customer_name: string
  event_date: string
  slot_label: string
  start_time: string
  end_time: string
  guest_count: number
  operation_label: string
  operation_status: string
  balance: string
}
type Occupancy = { event_date: string; events: number; capacity: number }
type View = "month" | "week" | "agenda"

const TYPES = [
  { status: "CONFIRMED", label: "Confirmada", color: "#3B82F6" },
  { status: "IN_PREP", label: "En preparación", color: "#F59E0B" },
  { status: "COMPLETED", label: "Cerrada", color: "#10B981" },
  { status: "CANCELLED", label: "Cancelada", color: "#F43F5E" },
]
const WEEKDAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
const MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

function iso(value: Date): string {
  const month = String(value.getMonth() + 1).padStart(2, "0")
  const day = String(value.getDate()).padStart(2, "0")
  return `${value.getFullYear()}-${month}-${day}`
}

function addDays(value: Date, days: number): Date {
  const next = new Date(value)
  next.setDate(next.getDate() + days)
  return next
}

function startOfWeek(value: Date): Date {
  const next = new Date(value)
  const offset = (next.getDay() + 6) % 7
  next.setDate(next.getDate() - offset)
  return next
}

function monthCells(anchor: Date): Date[] {
  const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1)
  const start = addDays(first, -((first.getDay() + 6) % 7))
  return Array.from({ length: 42 }, (_, index) => addDays(start, index))
}

function colorFor(status: string): string {
  return TYPES.find((item) => item.status === status)?.color ?? "#A1A1AA"
}

export function CalendarPage() {
  const reservations = useQuery({
    queryKey: ["reservations"],
    queryFn: () => api<{ reservations: Reservation[] }>("/reservations"),
  })
  const reports = useQuery({
    queryKey: ["reports"],
    queryFn: () => api<{ occupancy: Occupancy[] }>("/reports"),
  })
  const today = useMemo(() => new Date(), [])
  const [anchor, setAnchor] = useState(() => new Date())
  const [selected, setSelected] = useState(() => iso(new Date()))
  const [view, setView] = useState<View>("month")
  const [enabled, setEnabled] = useState(() => new Set(TYPES.map((item) => item.status)))
  const rows = reservations.data?.reservations ?? []
  const known = new Set(TYPES.map((item) => item.status))
  const visible = rows.filter((row) => !known.has(row.operation_status) || enabled.has(row.operation_status))
  const byDate = useMemo(() => {
    const map = new Map<string, Reservation[]>()
    for (const row of visible) {
      const key = row.event_date.slice(0, 10)
      map.set(key, [...(map.get(key) ?? []), row])
    }
    return map
  }, [visible])
  const overloaded = useMemo(() => {
    const dates = new Set<string>()
    for (const row of reports.data?.occupancy ?? []) {
      if (row.capacity > 0 && row.events > row.capacity) dates.add(row.event_date.slice(0, 10))
    }
    return dates
  }, [reports.data])
  const cells = view === "week" ? Array.from({ length: 7 }, (_, index) => addDays(startOfWeek(anchor), index)) : monthCells(anchor)
  const todayKey = iso(today)
  const upcoming = visible
    .filter((row) => row.event_date.slice(0, 10) >= todayKey)
    .sort((left, right) => left.event_date.localeCompare(right.event_date))
    .slice(0, 6)

  function move(direction: number) {
    const next = new Date(anchor)
    if (view === "week") next.setDate(next.getDate() + direction * 7)
    else next.setMonth(next.getMonth() + direction)
    setAnchor(next)
  }

  function toggle(status: string) {
    setEnabled((current) => {
      const next = new Set(current)
      if (next.has(status)) next.delete(status)
      else next.add(status)
      return next
    })
  }

  return (
    <div className="w-full space-y-6 px-4 py-8 sm:px-6 lg:px-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">Calendario</h1>
        <p className="mt-1 text-base text-zinc-400">Eventos del mes, con aviso cuando un horario supera la capacidad.</p>
      </div>
      <div className="flex flex-col gap-6 lg:flex-row">
        <aside className="w-full shrink-0 space-y-6 rounded-2xl border border-zinc-800/80 bg-zinc-900/90 p-4 lg:w-72">
          <MiniMonth
            anchor={anchor}
            selected={selected}
            today={todayKey}
            marked={byDate}
            overloaded={overloaded}
            onSelect={(day) => {
              setSelected(iso(day))
              setAnchor(day)
            }}
          />
          <div>
            <h2 className="text-lg font-semibold text-white">Tipo de evento</h2>
            <div className="mt-3 space-y-2">
              {TYPES.map((item) => (
                <label key={item.status} className="flex items-center gap-2 text-base text-zinc-200">
                  <input
                    type="checkbox"
                    className="size-4"
                    style={{ accentColor: item.color }}
                    checked={enabled.has(item.status)}
                    onChange={() => toggle(item.status)}
                  />
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: item.color }} />
                  {item.label}
                </label>
              ))}
            </div>
          </div>
          <div>
            <h2 className="text-lg font-semibold text-white">Próximos eventos</h2>
            <div className="mt-3 space-y-2">
              {upcoming.length === 0 ? (
                <p className="text-sm text-zinc-400">No hay eventos próximos con estos filtros.</p>
              ) : (
                upcoming.map((row) => (
                  <Link
                    key={row.id}
                    to={"/reservations/$reservationId" as never}
                    params={{ reservationId: row.id } as never}
                    className="block rounded-xl border border-zinc-800 bg-zinc-800/40 px-3 py-3"
                    style={{ borderLeftWidth: 4, borderLeftColor: colorFor(row.operation_status) }}
                  >
                    <span className="block text-base font-semibold text-white">{row.customer_name}</span>
                    <span className="mt-1 block text-sm text-zinc-400">
                      {row.event_date.slice(0, 10)} · {row.start_time}{row.end_time ? `–${row.end_time}` : ""} · {row.guest_count} invitados
                    </span>
                  </Link>
                ))
              )}
            </div>
          </div>
        </aside>
        <section className="min-w-0 flex-1 rounded-2xl border border-zinc-800/80 bg-zinc-900/90 p-4 sm:p-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2">
              <button type="button" className="grid h-10 w-10 place-items-center rounded-full border border-zinc-800 bg-zinc-800/70 text-zinc-100" onClick={() => move(-1)} aria-label="Periodo anterior">
                ‹
              </button>
              <h2 className="min-w-40 text-center text-lg font-semibold text-white capitalize">
                {view === "week" ? `Semana del ${iso(startOfWeek(anchor))}` : `${MONTHS[anchor.getMonth()]} ${anchor.getFullYear()}`}
              </h2>
              <button type="button" className="grid h-10 w-10 place-items-center rounded-full border border-zinc-800 bg-zinc-800/70 text-zinc-100" onClick={() => move(1)} aria-label="Periodo siguiente">
                ›
              </button>
            </div>
            <div className="flex rounded-xl bg-zinc-800/70 p-1">
              {(
                [
                  ["month", "Mes"],
                  ["week", "Semana"],
                  ["agenda", "Agenda"],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  className={`rounded-lg px-3 py-2 text-sm font-medium ${view === id ? "bg-accent text-accent-foreground" : "text-zinc-300"}`}
                  onClick={() => setView(id)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          {view === "agenda" ? (
            <Agenda rows={visible.filter((row) => row.event_date.slice(0, 7) === iso(anchor).slice(0, 7))} overloaded={overloaded} />
          ) : (
            <MonthGrid
              cells={cells}
              anchor={anchor}
              selected={selected}
              today={todayKey}
              byDate={byDate}
              overloaded={overloaded}
              compact={view === "month"}
              onSelect={(day) => setSelected(iso(day))}
            />
          )}
          {overloaded.has(selected) ? (
            <p className="mt-4 rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
              El {selected} tiene un horario por encima de la capacidad simultánea.
            </p>
          ) : null}
        </section>
      </div>
    </div>
  )
}

function MiniMonth({
  anchor,
  selected,
  today,
  marked,
  overloaded,
  onSelect,
}: {
  anchor: Date
  selected: string
  today: string
  marked: Map<string, Reservation[]>
  overloaded: Set<string>
  onSelect: (day: Date) => void
}) {
  return (
    <div>
      <p className="text-lg font-semibold text-white capitalize">
        {MONTHS[anchor.getMonth()]} {anchor.getFullYear()}
      </p>
      <div className="mt-3 grid grid-cols-7 gap-1 text-center text-sm text-zinc-400">
        {WEEKDAYS.map((day) => (
          <span key={day}>{day.slice(0, 1)}</span>
        ))}
        {monthCells(anchor).map((day) => {
          const key = iso(day)
          const outside = day.getMonth() !== anchor.getMonth()
          return (
            <button
              key={key}
              type="button"
              className={`relative grid h-8 place-items-center rounded-lg ${
                key === selected ? "bg-accent font-semibold text-accent-foreground" : outside ? "text-zinc-600" : "text-zinc-200"
              }`}
              onClick={() => onSelect(day)}
            >
              {day.getDate()}
              {marked.has(key) ? (
                <span className={`absolute bottom-1 h-1 w-1 rounded-full ${overloaded.has(key) ? "bg-rose-400" : "bg-blue-400"} ${key === selected ? "bg-accent-foreground" : ""}`} />
              ) : null}
              {key === today && key !== selected ? <span className="absolute inset-0 rounded-lg ring-1 ring-accent" /> : null}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function MonthGrid({
  cells,
  anchor,
  selected,
  today,
  byDate,
  overloaded,
  compact,
  onSelect,
}: {
  cells: Date[]
  anchor: Date
  selected: string
  today: string
  byDate: Map<string, Reservation[]>
  overloaded: Set<string>
  compact: boolean
  onSelect: (day: Date) => void
}) {
  return (
    <div className="mt-4">
      <div className="grid grid-cols-7 gap-2 text-sm text-zinc-400">
        {WEEKDAYS.map((day) => (
          <span key={day} className="px-2 py-1">
            {day}
          </span>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-2">
        {cells.map((day) => {
          const key = iso(day)
          const events = byDate.get(key) ?? []
          const outside = compact && day.getMonth() !== anchor.getMonth()
          return (
            <button
              key={key}
              type="button"
              className={`min-h-28 rounded-xl border p-2 text-left ${
                overloaded.has(key) ? "border-rose-500/70" : key === selected ? "border-accent" : "border-zinc-800"
              } ${outside ? "opacity-40" : ""} ${key === today ? "bg-zinc-800/50" : "bg-zinc-950/40"}`}
              onClick={() => onSelect(day)}
            >
              <span className="flex items-center justify-between text-sm text-zinc-300">
                {day.getDate()}
                {overloaded.has(key) ? <span className="text-rose-300">Sobrecupo</span> : null}
              </span>
              <span className="mt-2 block space-y-1">
                {events.slice(0, compact ? 2 : 4).map((row) => (
                  <span key={row.id} className="block truncate rounded-md px-1.5 py-1 text-sm text-white" style={{ background: `${colorFor(row.operation_status)}33` }}>
                    {row.start_time ? `${row.start_time} ` : ""}{row.customer_name}
                  </span>
                ))}
                {events.length > (compact ? 2 : 4) ? <span className="block text-sm text-zinc-400">+{events.length - (compact ? 2 : 4)}</span> : null}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function Agenda({ rows, overloaded }: { rows: Reservation[]; overloaded: Set<string> }) {
  const ordered = [...rows].sort((left, right) => left.event_date.localeCompare(right.event_date))
  if (ordered.length === 0) return <p className="py-10 text-base text-zinc-400">No hay eventos en este mes con los filtros activos.</p>
  return (
    <div className="mt-4 space-y-2">
      {ordered.map((row) => {
        const key = row.event_date.slice(0, 10)
        return (
          <Link
            key={row.id}
            to={"/reservations/$reservationId" as never}
            params={{ reservationId: row.id } as never}
            className="flex items-center justify-between gap-3 rounded-xl border border-zinc-800 bg-zinc-800/40 px-4 py-4"
            style={{ borderLeftWidth: 4, borderLeftColor: colorFor(row.operation_status) }}
          >
            <span>
              <span className="block text-base font-semibold text-white">{row.customer_name}</span>
              <span className="mt-1 block text-sm text-zinc-400">
                {key} · {row.start_time}{row.end_time ? `–${row.end_time}` : ""} · {row.guest_count} invitados · {row.operation_label}
              </span>
            </span>
            <span className="text-right">
              <span className="block text-sm tabular-nums text-zinc-200">{money(row.balance)}</span>
              {overloaded.has(key) ? <span className="text-sm text-rose-300">Sobrecupo</span> : null}
            </span>
          </Link>
        )
      })}
    </div>
  )
}
