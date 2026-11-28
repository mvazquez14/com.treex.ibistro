import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { Box, Calendar, ChartLine, Copy, FileText, Vault, Wallet } from "@gravity-ui/icons"
import { useMemo, useState } from "react"

import { api, money, type Session } from "@/api"
import { KpiMetricCard } from "@/components/ui-kit/KpiMetricCard"
import { Button } from "@/ui/controls"

type Profit = { customer_name: string; event_date: string; revenue: string; margin: string }
type Reports = {
  profitability: Profit[]
  restock: { ingredient_name: string; available_qty: number; min_stock: number }[]
  occupancy: { event_date: string; slot_label: string; events: number; capacity: number }[]
  pending: { customer_name: string; event_date: string; balance: string }[]
}
type Quote = { id: string; lead_name: string; package_name: string; guest_count: number; created_at?: string }
type Period = "7D" | "30D" | "90D" | "12M"
type Grain = "day" | "week" | "month"

const PERIODS: Period[] = ["7D", "30D", "90D", "12M"]
const GRAINS: { id: Grain; label: string }[] = [
  { id: "day", label: "Día" },
  { id: "week", label: "Semana" },
  { id: "month", label: "Mes" },
]
const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

function iso(value: Date): string {
  const month = String(value.getMonth() + 1).padStart(2, "0")
  const day = String(value.getDate()).padStart(2, "0")
  return `${value.getFullYear()}-${month}-${day}`
}

function inRange(value: string, start: string, end: string): boolean {
  return value.slice(0, 10) >= start && value.slice(0, 10) <= end
}

function sum(values: string[]): number {
  return values.reduce((total, value) => total + Number(value || 0), 0)
}

function periodWindow(period: Period, today: Date) {
  const length = period === "7D" ? 7 : period === "30D" ? 30 : period === "90D" ? 90 : 365
  const end = new Date(today)
  const start = new Date(today)
  start.setDate(start.getDate() - (length - 1))
  const previousEnd = new Date(start)
  previousEnd.setDate(previousEnd.getDate() - 1)
  const previousStart = new Date(previousEnd)
  previousStart.setDate(previousStart.getDate() - (length - 1))
  return {
    start: iso(start),
    end: iso(end),
    previousStart: iso(previousStart),
    previousEnd: iso(previousEnd),
  }
}

function trend(current: number, previous: number): { direction: "up" | "down" | "flat"; label: string } {
  if (previous === 0 && current === 0) return { direction: "flat", label: "0%" }
  if (previous === 0) return { direction: "up", label: "+100%" }
  const delta = ((current - previous) / Math.abs(previous)) * 100
  const direction = delta > 0.5 ? "up" : delta < -0.5 ? "down" : "flat"
  const sign = delta > 0 ? "+" : ""
  return { direction, label: `${sign}${delta.toFixed(1)}%` }
}

function greeting(date: Date): string {
  const hour = date.getHours()
  if (hour < 12) return "Buenos días"
  if (hour < 19) return "Buenas tardes"
  return "Buenas noches"
}

function shortDate(value: string): string {
  const date = new Date(`${value.slice(0, 10)}T12:00:00`)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString("es-MX", { day: "numeric", month: "short" })
}

function relativeTime(value: string | undefined): string {
  if (!value) return "sin fecha"
  const then = new Date(value).getTime()
  if (Number.isNaN(then)) return "sin fecha"
  const minutes = Math.max(0, Math.round((Date.now() - then) / 60000))
  if (minutes < 1) return "ahora"
  if (minutes < 60) return `hace ${minutes} min`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `hace ${hours} h`
  return `hace ${Math.round(hours / 24)} d`
}

function weekKey(value: string): string {
  const date = new Date(`${value.slice(0, 10)}T12:00:00`)
  const offset = (date.getDay() + 6) % 7
  date.setDate(date.getDate() - offset)
  return iso(date)
}

function bucketKey(value: string, grain: Grain): string {
  const day = value.slice(0, 10)
  if (grain === "month") return day.slice(0, 7)
  if (grain === "week") return weekKey(day)
  return day
}

function bucketLabel(key: string, grain: Grain): string {
  if (grain === "month") return MONTHS[Number(key.slice(5, 7)) - 1] ?? key
  if (grain === "week") return key.slice(5)
  return key.slice(8)
}

function axisMoney(value: number): string {
  if (Math.abs(value) >= 1000) return `$${(value / 1000).toFixed(value >= 10000 ? 0 : 1)}k`
  return money(value)
}

export function ExecutiveDashboard({ session }: { session: Session }) {
  const [period, setPeriod] = useState<Period>("30D")
  const [grain, setGrain] = useState<Grain>("day")
  const [copied, setCopied] = useState(false)
  const reports = useQuery({ queryKey: ["reports"], queryFn: () => api<Reports>("/reports") })
  const quotes = useQuery({ queryKey: ["quotes"], queryFn: () => api<Quote[]>("/quotes") })
  const data = reports.data
  const today = useMemo(() => new Date(), [])
  const window = useMemo(() => periodWindow(period, today), [period, today])
  const profits = (data?.profitability ?? []).filter((row) => inRange(row.event_date, window.start, window.end))
  const previousProfits = (data?.profitability ?? []).filter((row) =>
    inRange(row.event_date, window.previousStart, window.previousEnd),
  )
  const occupancy = (data?.occupancy ?? []).filter((row) => inRange(row.event_date, window.start, window.end))
  const previousOccupancy = (data?.occupancy ?? []).filter((row) =>
    inRange(row.event_date, window.previousStart, window.previousEnd),
  )
  const pending = (data?.pending ?? []).filter((row) => inRange(row.event_date, window.start, window.end))
  const previousPending = (data?.pending ?? []).filter((row) =>
    inRange(row.event_date, window.previousStart, window.previousEnd),
  )
  const revenue = sum(profits.map((row) => row.revenue))
  const previousRevenue = sum(previousProfits.map((row) => row.revenue))
  const margin = sum(profits.map((row) => row.margin))
  const previousMargin = sum(previousProfits.map((row) => row.margin))
  const events = occupancy.reduce((total, row) => total + row.events, 0)
  const previousEvents = previousOccupancy.reduce((total, row) => total + row.events, 0)
  const capacity = occupancy.reduce((total, row) => total + row.capacity, 0)
  const balance = sum(pending.map((row) => row.balance))
  const previousBalance = sum(previousPending.map((row) => row.balance))
  const occupancyRate = capacity ? Math.round((events / capacity) * 100) : 0
  const marginRate = revenue ? Math.round((margin / revenue) * 100) : 0
  const todayKey = iso(today)
  const todayEvents = (data?.occupancy ?? [])
    .filter((row) => row.event_date.slice(0, 10) === todayKey)
    .reduce((total, row) => total + row.events, 0)
  const revenuePoints = useMemo(() => {
    const buckets = new Map<string, number>()
    for (const row of profits) {
      const key = bucketKey(row.event_date, grain)
      buckets.set(key, (buckets.get(key) ?? 0) + Number(row.revenue || 0))
    }
    return [...buckets.entries()]
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, value]) => ({ label: bucketLabel(key, grain), value }))
  }, [profits, grain])
  const byCustomer = new Map<string, number>()
  for (const row of profits) byCustomer.set(row.customer_name, (byCustomer.get(row.customer_name) ?? 0) + Number(row.margin || 0))
  const customerBars = [...byCustomer.entries()]
    .sort((left, right) => right[1] - left[1])
    .slice(0, 6)
    .map(([label, value]) => ({ label, value }))
  const restock = (data?.restock ?? []).filter((row) => row.available_qty <= row.min_stock)
  const landing = session.slug ? `${session.public_base_url || ""}/c/${session.slug}` : ""

  async function copyLanding() {
    if (!landing) return
    await navigator.clipboard.writeText(landing)
    setCopied(true)
  }

  return (
    <div className="w-full space-y-6 px-4 py-8 sm:px-6 lg:px-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-5xl font-bold leading-none text-white">Dashboard</h1>
          <p className="mt-1 text-base text-zinc-400">
            {greeting(today)}.{" "}
            {todayEvents === 0
              ? "Hoy la agenda está libre."
              : `Hoy tienes ${todayEvents} evento${todayEvents === 1 ? "" : "s"} en agenda.`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex rounded-xl bg-background-tertiary p-1">
            {PERIODS.map((item) => (
              <button
                key={item}
                type="button"
                className={`rounded-lg px-3 py-2 text-sm font-medium ${
                  item === period ? "bg-accent text-accent-foreground" : "text-zinc-300"
                }`}
                onClick={() => setPeriod(item)}
              >
                {item}
              </button>
            ))}
          </div>
          <Button to="/reports" color="primary">
            Ver reportes
          </Button>
          {landing ? (
            <button type="button" className="inline-flex items-center gap-2 text-sm font-medium text-accent" onClick={() => void copyLanding()}>
              <Copy width={14} height={14} />
              {copied ? "Enlace copiado" : "Copiar micro-landing"}
            </button>
          ) : null}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiMetricCard label="Ingresos programados" value={money(revenue)} icon={<Wallet width={18} height={18} />} tone="warning" trend={trend(revenue, previousRevenue)} />
        <KpiMetricCard label="Margen" value={money(margin)} icon={<ChartLine width={18} height={18} />} tone="success" trend={trend(margin, previousMargin)} />
        <KpiMetricCard label="Ocupación" value={`${occupancyRate}%`} icon={<Calendar width={18} height={18} />} tone="info" trend={trend(events, previousEvents)} />
        <KpiMetricCard label="Por cobrar" value={money(balance)} icon={<Vault width={18} height={18} />} tone="danger" trend={trend(balance, previousBalance)} />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <section className="rounded-2xl border border-zinc-800/80 bg-background-secondary p-6 xl:col-span-2">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-4xl font-semibold leading-[1.11] text-white">Ingresos del periodo</h2>
              <p className="mt-1 text-sm text-zinc-400">Suma de los eventos con fecha en el periodo.</p>
            </div>
            <div className="flex rounded-xl bg-background-tertiary p-1">
              {GRAINS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`rounded-lg px-3 py-2 text-sm font-medium ${
                    item.id === grain ? "bg-accent text-accent-foreground" : "text-zinc-300"
                  }`}
                  onClick={() => setGrain(item.id)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
          <div className="mt-4">
            <RevenueArea points={revenuePoints} />
          </div>
        </section>
        <section className="rounded-2xl border border-zinc-800/80 bg-background-secondary p-6">
          <h2 className="text-4xl font-semibold leading-[1.11] text-white">Rentabilidad por cliente</h2>
          <p className="mt-1 text-sm text-zinc-400">Margen de los eventos del periodo.</p>
          <div className="mt-6">
            <RankList rows={customerBars} />
          </div>
        </section>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <section className="rounded-2xl border border-zinc-800/80 bg-background-secondary p-6">
          <h2 className="text-4xl font-semibold leading-[1.11] text-white">Actividad reciente</h2>
          <div className="mt-4">
            <ActivityList quotes={quotes.data ?? []} pending={pending} restock={restock} />
          </div>
        </section>
        <section className="rounded-2xl border border-zinc-800/80 bg-background-secondary p-6">
          <h2 className="text-4xl font-semibold leading-[1.11] text-white">Desempeño</h2>
          <p className="mt-1 text-sm text-zinc-400">Cifras del periodo seleccionado.</p>
          <div className="mt-6 grid grid-cols-2 gap-3">
            <PerformanceStat label="Ocupación" value={`${occupancyRate}%`} hint={`${events} de ${capacity} lugares`} />
            <PerformanceStat label="Margen" value={`${marginRate}%`} hint="sobre ingresos" />
            <PerformanceStat label="Eventos" value={String(events)} hint="en el periodo" />
            <PerformanceStat label="En reorden" value={String(restock.length)} hint="insumos en el mínimo" />
          </div>
        </section>
      </div>
    </div>
  )
}

function RevenueArea({ points }: { points: { label: string; value: number }[] }) {
  const [active, setActive] = useState<number | null>(null)
  if (points.length === 0) return <p className="py-16 text-base text-zinc-400">Sin ingresos en este periodo.</p>
  const width = 640
  const height = 260
  const pad = { l: 56, r: 16, t: 20, b: 32 }
  const max = Math.max(...points.map((point) => point.value), 1)
  const innerW = width - pad.l - pad.r
  const innerH = height - pad.t - pad.b
  const coords = points.map((point, index) => {
    const x = pad.l + (points.length === 1 ? innerW / 2 : (index / (points.length - 1)) * innerW)
    const y = pad.t + innerH - (Math.max(point.value, 0) / max) * innerH
    return { ...point, x, y }
  })
  const line = coords.map((point) => `${point.x},${point.y}`).join(" ")
  const area = `${coords[0]?.x ?? pad.l},${pad.t + innerH} ${line} ${coords[coords.length - 1]?.x ?? pad.l},${pad.t + innerH}`
  const ticks = [0, max / 2, max]
  const labelStep = Math.max(1, Math.ceil(points.length / 8))
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-64 w-full" role="img" aria-label="Ingresos del periodo">
      {ticks.map((tick) => {
        const y = pad.t + innerH - (tick / max) * innerH
        return (
          <g key={tick}>
            <line x1={pad.l} x2={width - pad.r} y1={y} y2={y} stroke="#3f3f46" strokeDasharray="4 4" />
            <text x={pad.l - 8} y={y + 4} textAnchor="end" fill="#a1a1aa" fontSize="12">
              {axisMoney(tick)}
            </text>
          </g>
        )
      })}
      <polygon points={area} fill="#3B82F6" opacity="0.18" />
      {coords.length > 1 ? <polyline points={line} fill="none" stroke="#3B82F6" strokeWidth="2.5" /> : null}
      {coords.map((point, index) => (
        <g key={`${point.label}-${index}`} onMouseEnter={() => setActive(index)} onMouseLeave={() => setActive(null)}>
          <circle cx={point.x} cy={point.y} r="12" fill="transparent" />
          <circle cx={point.x} cy={point.y} r={active === index ? 5 : 3.5} fill="#3B82F6" />
          {index % labelStep === 0 ? (
            <text x={point.x} y={height - 8} textAnchor="middle" fill="#a1a1aa" fontSize="12">
              {point.label}
            </text>
          ) : null}
          {active === index ? (
            <text x={point.x} y={Math.max(14, point.y - 10)} textAnchor="middle" fill="#ffffff" fontSize="12">
              {money(point.value)}
            </text>
          ) : null}
        </g>
      ))}
    </svg>
  )
}

function RankList({ rows }: { rows: { label: string; value: number }[] }) {
  if (rows.length === 0) return <p className="py-10 text-base text-zinc-400">Sin margen en este periodo.</p>
  const max = Math.max(...rows.map((row) => row.value), 0)
  return (
    <ul className="space-y-5">
      {rows.map((row) => (
        <li key={row.label}>
          <div className="flex items-center justify-between gap-3">
            <span className="truncate text-base text-white">{row.label}</span>
            <span className="shrink-0 text-sm tabular-nums text-zinc-300">{money(row.value)}</span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-zinc-800">
            <div
              className="h-full rounded-full bg-[#3B82F6]"
              style={{ width: `${max > 0 ? Math.max(0, (row.value / max) * 100) : 0}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  )
}

function ActivityList({
  quotes,
  pending,
  restock,
}: {
  quotes: Quote[]
  pending: Reports["pending"]
  restock: Reports["restock"]
}) {
  const items = [
    ...quotes.slice(0, 4).map((row) => ({
      id: `quote-${row.id}`,
      title: row.lead_name,
      detail: `${row.package_name} · ${row.guest_count} invitados`,
      when: relativeTime(row.created_at),
      href: `/quotes/${row.id}`,
      icon: <FileText width={16} height={16} />,
      tone: "bg-accent-soft text-accent",
    })),
    ...pending.slice(0, 3).map((row) => ({
      id: `pending-${row.customer_name}-${row.event_date}`,
      title: row.customer_name,
      detail: `Saldo ${money(row.balance)}`,
      when: shortDate(row.event_date),
      href: "",
      icon: <Vault width={16} height={16} />,
      tone: "bg-warning-soft text-warning",
    })),
    ...restock.slice(0, 3).map((row) => ({
      id: `restock-${row.ingredient_name}`,
      title: row.ingredient_name,
      detail: `${row.available_qty} de ${row.min_stock} mínimo`,
      when: "en el mínimo",
      href: "",
      icon: <Box width={16} height={16} />,
      tone: "bg-danger-soft text-danger",
    })),
  ].slice(0, 8)
  if (items.length === 0) return <p className="py-8 text-base text-zinc-400">No hay solicitudes, saldos ni insumos en reorden.</p>
  return (
    <ul className="divide-y divide-zinc-800/80">
      {items.map((item) => {
        const body = (
          <>
            <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${item.tone}`}>{item.icon}</span>
            <span className="min-w-0 flex-1">
              <span className="flex items-start justify-between gap-3">
                <span className="truncate text-base font-semibold text-white">{item.title}</span>
                <span className="shrink-0 text-sm text-zinc-400">{item.when}</span>
              </span>
              <span className="mt-1 block truncate text-sm text-zinc-400">{item.detail}</span>
            </span>
          </>
        )
        return (
          <li key={item.id} className="py-3">
            {item.href ? (
              <Link to={item.href as never} className="flex items-center gap-3">
                {body}
              </Link>
            ) : (
              <div className="flex items-center gap-3">{body}</div>
            )}
          </li>
        )
      })}
    </ul>
  )
}

function PerformanceStat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-xl bg-zinc-800/70 p-4">
      <p className="text-2xl font-bold tracking-tight text-white tabular-nums">{value}</p>
      <p className="mt-1 text-sm font-medium text-zinc-200">{label}</p>
      <p className="mt-1 text-sm text-zinc-400">{hint}</p>
    </div>
  )
}
