import { Badge, Popover, toast } from "@heroui/react"
import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { Bell } from "@gravity-ui/icons"
import { useEffect, useMemo, useState } from "react"

import { api, money } from "@/api"
import { Button } from "@/ui/controls"

type QuoteNotice = {
  id: string
  lead_name: string
  package_name: string
  event_date: string
  guest_count: number
  total_amount: string
  created_at?: string
}

type Notice = QuoteNotice & { simulated?: boolean }

const READ_KEY = "ibistro.notifications.read"
const SEEN_KEY = "ibistro.notifications.seen"

function loadSet(key: string): Set<string> {
  try {
    const raw = localStorage.getItem(key)
    const parsed = raw ? (JSON.parse(raw) as unknown) : []
    return new Set(Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string") : [])
  } catch {
    return new Set()
  }
}

function saveSet(key: string, values: Set<string>) {
  localStorage.setItem(key, JSON.stringify([...values]))
}

function formatDate(value: string): string {
  const date = new Date(`${value.slice(0, 10)}T12:00:00`)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString("es-MX", { day: "numeric", month: "short" })
}

function relativeTime(value: string | undefined): string {
  if (!value) return "reciente"
  const then = new Date(value).getTime()
  if (Number.isNaN(then)) return "reciente"
  const minutes = Math.max(0, Math.round((Date.now() - then) / 60000))
  if (minutes < 1) return "ahora"
  if (minutes < 60) return `hace ${minutes} min`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `hace ${hours} h`
  return `hace ${Math.round(hours / 24)} d`
}

function announce(row: Notice, open: (id: string) => void) {
  const fecha = formatDate(row.event_date)
  toast.success("Nueva solicitud recibida", {
    description: `${row.lead_name} solicitó cotización para ${row.guest_count} invitados (${fecha}).`,
    timeout: 6000,
    actionProps: {
      children: "Ver solicitud",
      variant: "tertiary",
      onPress: () => open(row.id),
    },
  })
}

export function NotificationBell() {
  const navigate = useNavigate()
  const quotes = useQuery({
    queryKey: ["quotes"],
    queryFn: () => api<QuoteNotice[]>("/quotes"),
    refetchInterval: 20_000,
  })
  const [simulated, setSimulated] = useState<Notice[]>([])
  const [read, setRead] = useState<Set<string>>(() => loadSet(READ_KEY))
  const [open, setOpen] = useState(false)
  const demo =
    import.meta.env.DEV ||
    window.location.hostname === "localhost" ||
    window.location.hostname.includes("test")

  function openQuote(id: string) {
    setRead((current) => {
      const next = new Set(current)
      next.add(id)
      saveSet(READ_KEY, next)
      return next
    })
    setOpen(false)
    if (id.startsWith("sim-")) {
      void navigate({ to: "/quotes" })
      return
    }
    void navigate({ to: "/quotes/$quoteId", params: { quoteId: id } })
  }

  useEffect(() => {
    const rows = quotes.data
    if (!rows) return
    if (localStorage.getItem(SEEN_KEY) === null) {
      const ids = new Set(rows.map((row) => row.id))
      saveSet(SEEN_KEY, ids)
      const already = loadSet(READ_KEY)
      for (const id of ids) already.add(id)
      saveSet(READ_KEY, already)
      setRead(already)
      return
    }
    const known = loadSet(SEEN_KEY)
    const fresh = rows.filter((row) => !known.has(row.id))
    if (fresh.length === 0) return
    for (const row of fresh) announce(row, openQuote)
    saveSet(SEEN_KEY, new Set([...known, ...fresh.map((row) => row.id)]))
  }, [quotes.data])

  const items = useMemo(() => [...simulated, ...(quotes.data ?? [])], [quotes.data, simulated])
  const unread = items.filter((item) => !read.has(item.id)).length

  function markAll() {
    const next = new Set(read)
    for (const item of items) next.add(item.id)
    saveSet(READ_KEY, next)
    setRead(next)
  }

  function simulate() {
    const row: Notice = {
      id: `sim-${Date.now()}`,
      lead_name: "Ana López",
      package_name: "Taquiza",
      event_date: new Date().toISOString().slice(0, 10),
      guest_count: 80,
      total_amount: "24000.00",
      created_at: new Date().toISOString(),
      simulated: true,
    }
    setSimulated((current) => [row, ...current])
    announce(row, openQuote)
  }

  return (
    <Popover isOpen={open} onOpenChange={setOpen}>
      <Popover.Trigger
        aria-label="Notificaciones"
        className="relative inline-flex h-10 w-10 min-w-10 cursor-pointer items-center justify-center rounded-full border border-zinc-800 bg-zinc-900 text-zinc-200 hover:bg-zinc-800"
      >
        <Badge.Anchor className="inline-flex h-full w-full items-center justify-center">
          <Bell width={20} height={20} className="h-5 w-5 text-zinc-200" />
          {unread > 0 ? (
            <Badge
              color="warning"
              size="sm"
              placement="top-right"
              className="h-5 min-h-5 min-w-5 px-1 text-xs font-bold text-zinc-950"
            >
              {unread}
            </Badge>
          ) : null}
        </Badge.Anchor>
      </Popover.Trigger>
      <Popover.Content
        placement="bottom end"
        className="w-96 max-w-[calc(100vw-2rem)] rounded-2xl border border-zinc-800/80 bg-background-secondary p-0 shadow-2xl"
      >
        <Popover.Dialog className="p-0 outline-none">
          <div className="flex items-center justify-between gap-3 border-b border-zinc-800 px-4 py-3">
            <div>
              <p className="text-base font-semibold text-white">Notificaciones</p>
              <p className="text-sm text-zinc-400">{unread} nuevas</p>
            </div>
            <button type="button" className="text-sm font-medium text-accent" onClick={markAll}>
              Marcar leídas
            </button>
          </div>
          <div className="max-h-96 overflow-y-auto">
            {items.length === 0 ? (
              <p className="px-4 py-8 text-sm text-zinc-400">No hay solicitudes recientes.</p>
            ) : (
              items.map((item) => {
                const unreadItem = !read.has(item.id)
                return (
                  <button
                    key={item.id}
                    type="button"
                    className={`flex w-full gap-3 border-b border-zinc-800/60 px-4 py-4 text-left ${
                      unreadItem ? "bg-zinc-800/40" : ""
                    }`}
                    onClick={() => openQuote(item.id)}
                  >
                    <span
                      className={`mt-2 size-2 shrink-0 rounded-full ${
                        unreadItem ? "bg-accent" : "bg-transparent"
                      }`}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="flex items-start justify-between gap-3">
                        <span className="truncate text-base font-semibold text-white">{item.lead_name}</span>
                        <span className="shrink-0 text-sm text-zinc-400">{relativeTime(item.created_at)}</span>
                      </span>
                      <span className="mt-1 block text-sm text-zinc-400">
                        {item.package_name} · {formatDate(item.event_date)} · {item.guest_count} invitados
                      </span>
                      <span className="mt-1 block text-sm tabular-nums text-zinc-200">
                        {money(item.total_amount)}
                      </span>
                    </span>
                  </button>
                )
              })
            )}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-800 px-4 py-3">
            <Button
              variant="light"
              onPress={() => {
                setOpen(false)
                void navigate({ to: "/quotes" })
              }}
            >
              Ver todas las solicitudes
            </Button>
            {demo ? (
              <button type="button" className="text-sm text-zinc-400" onClick={simulate}>
                Simular nueva solicitud
              </button>
            ) : null}
          </div>
        </Popover.Dialog>
      </Popover.Content>
    </Popover>
  )
}
