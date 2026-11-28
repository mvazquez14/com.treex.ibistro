import { Accordion, Avatar, Dropdown, Label } from "@heroui/react"
import {
  Bars,
  Box,
  Boxes3,
  Calendar,
  Car,
  ChartColumn,
  Cookie,
  Cup,
  Factory,
  File,
  FileText,
  Gear,
  House,
  LayoutCells,
  ListUl,
  Magnifier,
  ShoppingBag,
  Tag,
} from "@gravity-ui/icons"
import { Link, useNavigate, useRouterState } from "@tanstack/react-router"
import type { ReactNode } from "react"
import { useState } from "react"

import type { Session } from "@/api"
import { NotificationBell } from "@/components/shell/Notifications"
import { Button, Input } from "@/ui/controls"

type Item = { to: string; label: string; icon: ReactNode }

const groups: { title: string; items: Item[] }[] = [
  {
    title: "Operación",
    items: [
      { to: "/calendario", label: "Calendario", icon: <Calendar width={18} height={18} /> },
      { to: "/reservations", label: "Reservaciones", icon: <ListUl width={18} height={18} /> },
      { to: "/quotes", label: "Cotizaciones", icon: <FileText width={18} height={18} /> },
      { to: "/pos", label: "Punto de Venta (POS)", icon: <ShoppingBag width={18} height={18} /> },
    ],
  },
  {
    title: "Menú y Costos",
    items: [
      { to: "/menu/recipes", label: "Recetas y Costeo", icon: <Cup width={18} height={18} /> },
      { to: "/menu/packages", label: "Paquetes", icon: <Box width={18} height={18} /> },
      { to: "/menu/groups", label: "Grupos de variantes", icon: <LayoutCells width={18} height={18} /> },
      { to: "/menu/extras", label: "Extras", icon: <Cookie width={18} height={18} /> },
      { to: "/menu/categories", label: "Categorías", icon: <Tag width={18} height={18} /> },
    ],
  },
  {
    title: "Recursos",
    items: [
      { to: "/warehouses", label: "Almacenes e insumos", icon: <Boxes3 width={18} height={18} /> },
      { to: "/ingredients", label: "Insumos", icon: <ListUl width={18} height={18} /> },
      { to: "/equipment", label: "Equipo y mantelería", icon: <Factory width={18} height={18} /> },
      { to: "/suppliers", label: "Proveedores", icon: <Car width={18} height={18} /> },
    ],
  },
  {
    title: "Administración",
    items: [
      { to: "/reports", label: "Reportes", icon: <ChartColumn width={18} height={18} /> },
      { to: "/settings", label: "Configuración", icon: <Gear width={18} height={18} /> },
    ],
  },
]

const dashboardItem: Item = { to: "/", label: "Dashboard", icon: <House width={18} height={18} /> }

function NavItem({ item, collapsed }: { item: Item; collapsed: boolean }) {
  const path = useRouterState({ select: (state) => state.location.pathname })
  const active = item.to === "/" ? path === "/" : path === item.to || path.startsWith(`${item.to}/`)
  return (
    <Link
      to={item.to as never}
      className={`flex items-center gap-3 rounded-lg px-3 py-2 text-base ${
        active ? "bg-accent font-bold text-accent-foreground" : "text-zinc-300 hover:bg-background-tertiary"
      }`}
      title={item.label}
    >
      {item.icon}
      {collapsed ? null : <span className="truncate">{item.label}</span>}
    </Link>
  )
}

export function AppShell({ session, children }: { session: Session; children: ReactNode }) {
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(false)
  const [search, setSearch] = useState("")
  const landing = session.slug ? `${session.public_base_url || ""}/c/${session.slug}` : ""
  const initial = (session.business_name || "I").slice(0, 1).toUpperCase()
  const catalog = [dashboardItem, ...groups.flatMap((group) => group.items)]

  function goSearch() {
    const needle = search.trim().toLowerCase()
    if (!needle) return
    const hit = catalog.find((item) => item.label.toLowerCase().includes(needle))
    if (hit) void navigate({ to: hit.to as never })
  }

  return (
    <div className="flex min-h-screen bg-background text-zinc-100">
      <aside className={`flex shrink-0 flex-col border-r border-zinc-800 bg-background-secondary ${collapsed ? "w-[72px]" : "w-[250px]"}`}>
        <div className="flex h-16 items-center gap-2 px-4">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-accent font-black text-accent-foreground">iB</span>
          {collapsed ? null : <span className="text-lg font-semibold text-accent">iBistro</span>}
        </div>
        <nav className="flex-1 overflow-y-auto px-2">
          <div className="mb-2">
            <NavItem item={dashboardItem} collapsed={collapsed} />
          </div>
          {collapsed ? (
            <div className="flex flex-col gap-1">
              {groups.flatMap((group) => group.items.map((item) => <NavItem key={item.to} item={item} collapsed />))}
            </div>
          ) : (
            <Accordion defaultExpandedKeys={groups.map((group) => group.title)}>
              {groups.map((group) => (
                <Accordion.Item key={group.title} id={group.title}>
                  <Accordion.Heading>
                    <Accordion.Trigger>
                      <span className="text-sm font-medium text-zinc-400">{group.title}</span>
                      <Accordion.Indicator />
                    </Accordion.Trigger>
                  </Accordion.Heading>
                  <Accordion.Panel>
                    <div className="flex flex-col gap-1 pb-2">
                      {group.items.map((item) => (
                        <NavItem key={item.to} item={item} collapsed={false} />
                      ))}
                    </div>
                  </Accordion.Panel>
                </Accordion.Item>
              ))}
            </Accordion>
          )}
        </nav>
        <div className="border-t border-zinc-800 p-2">
          <a
            href={session.billing_url || "#"}
            className="flex items-center gap-3 rounded-lg px-3 py-2 text-base text-zinc-300 hover:bg-background-tertiary"
          >
            <File width={18} height={18} />
            {collapsed ? null : "Facturación Nuna"}
          </a>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        {session.impersonating ? (
          <div className="bg-accent px-4 py-2 text-center text-sm font-medium text-accent-foreground">
            Viendo la cuenta de {session.impersonating}.
            <form className="inline" method="post" action="/admin/impersonate/stop">
              <button className="ml-2 underline" type="submit">
                Volver al admin
              </button>
            </form>
          </div>
        ) : null}
        <header className="flex h-16 shrink-0 items-center gap-3 overflow-x-auto border-b border-zinc-800 px-4">
          <Button isIconOnly variant="light" aria-label="Colapsar menú" onPress={() => setCollapsed((value) => !value)}>
            <Bars width={18} height={18} />
          </Button>
          <Input
            label="Buscar"
            hideLabel
            placeholder="Buscar"
            startContent={<Magnifier width={16} height={16} />}
            value={search}
            onValueChange={setSearch}
            onKeyDown={(event) => {
              if (event.key === "Enter") goSearch()
            }}
            className="hidden w-72 md:block"
          />
          <div className="ml-auto flex min-w-0 items-center gap-3">
            <Button to="/" variant="flat" startContent={<House width={16} height={16} />}>
              Dashboard
            </Button>
            <Button to="/calendario" variant="light" isIconOnly aria-label="Calendario" className="h-10 w-10 min-w-10 rounded-full border border-zinc-800 bg-background-tertiary px-0">
              <Calendar width={18} height={18} />
            </Button>
            {landing ? (
              <a
                href={landing}
                target="_blank"
                rel="noreferrer"
                aria-label="Ver micro-landing"
                className="inline-flex h-10 w-10 min-w-10 items-center justify-center rounded-full border border-zinc-800 bg-background-tertiary text-zinc-200 hover:bg-default"
              >
                ↗
              </a>
            ) : null}
            <NotificationBell />
            <span className="inline-flex h-10 items-center whitespace-nowrap rounded-full border border-zinc-800 bg-background-tertiary px-3 text-sm text-zinc-100">
              {session.business_name}
            </span>
            <Dropdown>
              <Button aria-label="Cuenta" variant="light" isIconOnly className="h-10 w-10 min-w-10 rounded-full border border-zinc-800 bg-background-tertiary">
                <Avatar>
                  <Avatar.Fallback>{initial}</Avatar.Fallback>
                </Avatar>
              </Button>
              <Dropdown.Popover>
                <Dropdown.Menu>
                  <Dropdown.Item id="profile" href="/dashboard/settings" textValue="Perfil">
                    <Label>Perfil</Label>
                  </Dropdown.Item>
                  <Dropdown.Item id="nuna" href={session.billing_url} textValue="Sincronizar Nuna">
                    <Label>Sincronizar Nuna</Label>
                  </Dropdown.Item>
                  <Dropdown.Item id="logout" href="/api/auth/logout" textValue="Cerrar sesión">
                    <Label>Cerrar sesión</Label>
                  </Dropdown.Item>
                </Dropdown.Menu>
              </Dropdown.Popover>
            </Dropdown>
          </div>
        </header>
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  )
}
