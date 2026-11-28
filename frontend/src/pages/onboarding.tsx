import { Time } from "@internationalized/date"
import {
  Button,
  Card,
  Checkbox,
  CheckboxGroup,
  Description,
  Input,
  InputGroup,
  Label,
  NumberField,
  Switch,
  TextArea,
  TextField,
  TimeField,
} from "@heroui/react"
import { Comment as MessageCircle, Link as Link2, Smartphone as Phone } from "@gravity-ui/icons"
import { useEffect, useState } from "react"

import { LogoDropZone } from "@/pages/onboarding-dropzone"

type DayState = {
  id: number
  label: string
  active: boolean
  start: string
  end: string
}

type WizardState = {
  business_name: string
  rfc: string
  address: string
  min_guests: number
  max_guests: number
  whatsapp_phone: string
  contact_phone: string
  show_prices_public: boolean
  max_concurrent_events_per_slot: number
  accepts_cash: boolean
  accepts_transfer: boolean
  transfer_instructions: string
  categories: string[]
  selected_categories: string[]
  days: Array<{ id: number; label: string }>
  public_base_url: string
  slug: string
  slug_error: string
}

const STEPS = [
  { id: 1, title: "Tu marca" },
  { id: 2, title: "Cómo atiendes" },
  { id: 3, title: "Horario y cobro" },
]

const field = { variant: "secondary" as const, fullWidth: true }

function clock(value: string): Time {
  const [hour, minute] = value.split(":").map((part) => Number(part))
  return new Time(hour || 0, minute || 0)
}

function formatClock(value: { hour: number; minute: number } | null, fallback: string): string {
  if (!value) return fallback
  return `${String(value.hour).padStart(2, "0")}:${String(value.minute).padStart(2, "0")}`
}

export function OnboardingWizard() {
  const [step, setStep] = useState(1)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [name, setName] = useState("")
  const [rfc, setRfc] = useState("")
  const [address, setAddress] = useState("")
  const [logo, setLogo] = useState<File | null>(null)
  const [slug, setSlug] = useState("")
  const [slugError, setSlugError] = useState("")
  const [baseUrl, setBaseUrl] = useState("")
  const [categories, setCategories] = useState<string[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [minGuests, setMinGuests] = useState(20)
  const [maxGuests, setMaxGuests] = useState(300)
  const [whatsapp, setWhatsapp] = useState("")
  const [contact, setContact] = useState("")
  const [samePhone, setSamePhone] = useState(false)
  const [prices, setPrices] = useState(true)
  const [days, setDays] = useState<DayState[]>([])
  const [concurrent, setConcurrent] = useState(1)
  const [payments, setPayments] = useState<string[]>(["cash", "transfer"])
  const [instructions, setInstructions] = useState("")

  useEffect(() => {
    void fetch("/onboarding/state", { credentials: "include" })
      .then(async (response) => {
        if (response.redirected || response.status === 401) {
          window.location.assign("/login")
          return null
        }
        if (!response.ok) return null
        return (await response.json()) as WizardState
      })
      .then((payload) => {
        if (!payload) return
        setName(payload.business_name)
        setRfc(payload.rfc)
        setAddress(payload.address)
        setSlug(payload.slug)
        setSlugError(payload.slug_error)
        setBaseUrl(payload.public_base_url)
        setCategories(payload.categories)
        setSelected(payload.selected_categories)
        setMinGuests(payload.min_guests)
        setMaxGuests(payload.max_guests)
        setWhatsapp(payload.whatsapp_phone)
        setContact(payload.contact_phone)
        setPrices(payload.show_prices_public)
        setConcurrent(payload.max_concurrent_events_per_slot)
        setInstructions(payload.transfer_instructions)
        setPayments([
          ...(payload.accepts_cash ? ["cash"] : []),
          ...(payload.accepts_transfer ? ["transfer"] : []),
        ])
        setDays(
          payload.days.map((day) => ({
            ...day,
            active: false,
            start: "10:00",
            end: "18:00",
          })),
        )
      })
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams({
        business_name: name,
        response_format: "json",
      })
      void fetch(`/onboarding/slug?${params.toString()}`, { credentials: "include" })
        .then(async (response) => {
          if (!response.ok) return null
          return (await response.json()) as { slug: string; error: string }
        })
        .then((payload) => {
          if (!payload) return
          setSlug(payload.slug)
          setSlugError(payload.error)
        })
    }, 300)
    return () => window.clearTimeout(timer)
  }, [name])

  function applyMonday() {
    const monday = days.find((day) => day.id === 0)
    if (!monday) return
    setDays((current) =>
      current.map((day) => ({
        ...day,
        active: true,
        start: monday.start,
        end: monday.end,
      })),
    )
  }

  async function finish() {
    setBusy(true)
    setError("")
    const body = new FormData()
    body.set("business_name", name)
    body.set("rfc", rfc)
    body.set("address", address)
    body.set("min_guests", String(minGuests))
    body.set("max_guests", String(maxGuests))
    body.set("whatsapp_phone", whatsapp)
    body.set("contact_phone", samePhone ? whatsapp : contact)
    body.set("max_concurrent_events_per_slot", String(concurrent))
    body.set("transfer_instructions", instructions)
    if (prices) body.set("show_prices_public", "on")
    if (payments.includes("cash")) body.set("accepts_cash", "on")
    if (payments.includes("transfer")) body.set("accepts_transfer", "on")
    for (const category of selected) body.append("category", category)
    for (const day of days) {
      if (!day.active) continue
      body.set(`day_${day.id}`, "on")
      body.set(`start_${day.id}`, day.start)
      body.set(`end_${day.id}`, day.end)
    }
    if (logo) body.set("logo", logo)
    const response = await fetch("/onboarding/complete", {
      method: "POST",
      body,
      credentials: "include",
      headers: { Accept: "application/json" },
    })
    const payload = (await response.json()) as { detail?: string; redirect?: string }
    setBusy(false)
    if (!response.ok) {
      setError(payload.detail || "Revisa el formulario")
      return
    }
    window.location.assign(payload.redirect || "/dashboard")
  }

  const preview = slugError || `Tu micro-landing: ${baseUrl}/c/${slug}`

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 bg-background px-4 py-10 text-zinc-100">
      <header className="flex flex-col gap-4">
        <p className="text-sm text-accent">iBistro</p>
        <h1 className="text-5xl font-bold leading-none">Configura tu negocio</h1>
        <ol className="grid gap-2 sm:grid-cols-3">
          {STEPS.map((item) => (
            <li
              key={item.id}
              className={`rounded-xl border px-3 py-2 text-sm ${
                step === item.id
                  ? "border-accent bg-accent/10 text-accent"
                  : "border-zinc-700 text-zinc-400"
              }`}
            >
              {item.id}. {item.title}
            </li>
          ))}
        </ol>
        {error ? (
          <p className="rounded-lg border border-red-500 px-3 py-2 text-red-300">{error}</p>
        ) : null}
      </header>

      {step === 1 ? (
        <Card>
          <Card.Header>
            <Card.Title>Tu marca</Card.Title>
          </Card.Header>
          <Card.Content className="flex flex-col gap-6">
            <TextField {...field} value={name} onChange={setName}>
              <Label>Nombre del negocio</Label>
              <Input {...field} />
              <Description className={slugError ? "text-red-400" : undefined}>
                <span className="inline-flex items-center gap-2">
                  <Link2 className="size-4" />
                  {preview}
                </span>
              </Description>
            </TextField>
            <TextField
              {...field}
              value={rfc}
              onChange={(value) => setRfc(value.toUpperCase())}
            >
              <Label>RFC</Label>
              <Input {...field} placeholder="XAXX010101000" />
            </TextField>
            <TextField {...field} value={address} onChange={setAddress}>
              <Label>Dirección</Label>
              <TextArea {...field} rows={2} />
            </TextField>
            <LogoDropZone file={logo} onFile={setLogo} />
          </Card.Content>
        </Card>
      ) : null}

      {step === 2 ? (
        <div className="flex flex-col gap-6">
          <Card>
            <Card.Header>
              <Card.Title>Tipos de cocina</Card.Title>
            </Card.Header>
            <Card.Content>
              <CheckboxGroup
                variant="secondary"
                value={selected}
                onChange={setSelected}
                className="grid gap-3 sm:grid-cols-2"
              >
                {categories.map((category) => (
                  <Checkbox
                    key={category}
                    value={category}
                    variant="secondary"
                    className="rounded-xl border border-zinc-700 p-3 data-[selected=true]:border-accent"
                  >
                    <Checkbox.Content>
                      <Checkbox.Control>
                        <Checkbox.Indicator />
                      </Checkbox.Control>
                      {category}
                    </Checkbox.Content>
                  </Checkbox>
                ))}
              </CheckboxGroup>
            </Card.Content>
          </Card>
          <Card>
            <Card.Header>
              <Card.Title>Capacidad y contacto</Card.Title>
            </Card.Header>
            <Card.Content className="flex flex-col gap-6">
              <div className="grid gap-4 sm:grid-cols-2">
                <NumberField
                  {...field}
                  minValue={1}
                  value={minGuests}
                  onChange={(value) => setMinGuests(value)}
                >
                  <Label>Mínimo de invitados</Label>
                  <NumberField.Group>
                    <NumberField.Input />
                  </NumberField.Group>
                </NumberField>
                <NumberField
                  {...field}
                  minValue={1}
                  value={maxGuests}
                  onChange={(value) => setMaxGuests(value)}
                >
                  <Label>Máximo de invitados</Label>
                  <NumberField.Group>
                    <NumberField.Input />
                  </NumberField.Group>
                </NumberField>
              </div>
              <TextField
                {...field}
                type="tel"
                value={whatsapp}
                onChange={(value) => {
                  setWhatsapp(value)
                  if (samePhone) setContact(value)
                }}
              >
                <Label>WhatsApp</Label>
                <InputGroup {...field}>
                  <InputGroup.Prefix>
                    <MessageCircle className="size-4" />
                  </InputGroup.Prefix>
                  <InputGroup.Input placeholder="+523312345678" />
                </InputGroup>
              </TextField>
              <Checkbox
                variant="secondary"
                isSelected={samePhone}
                onChange={(selectedPhone) => {
                  setSamePhone(selectedPhone)
                  if (selectedPhone) setContact(whatsapp)
                }}
              >
                <Checkbox.Content>
                  <Checkbox.Control>
                    <Checkbox.Indicator />
                  </Checkbox.Control>
                  Usar el mismo número de WhatsApp
                </Checkbox.Content>
              </Checkbox>
              <TextField {...field} type="tel" value={contact} onChange={setContact} isDisabled={samePhone}>
                <Label>Teléfono de contacto</Label>
                <InputGroup {...field}>
                  <InputGroup.Prefix>
                    <Phone className="size-4" />
                  </InputGroup.Prefix>
                  <InputGroup.Input placeholder="+523312345678" />
                </InputGroup>
              </TextField>
              <Switch isSelected={prices} onChange={setPrices}>
                <Switch.Content>
                  <Switch.Control>
                    <Switch.Thumb />
                  </Switch.Control>
                  <span>
                    Mostrar precios en la micro-landing
                    <span className="mt-1 block text-sm text-zinc-400">
                      Los invitados verán el precio de paquetes y extras antes de cotizar.
                    </span>
                  </span>
                </Switch.Content>
              </Switch>
            </Card.Content>
          </Card>
        </div>
      ) : null}

      {step === 3 ? (
        <div className="flex flex-col gap-6">
          <Card>
            <Card.Header className="flex items-center justify-between gap-3">
              <Card.Title>Horarios de atención</Card.Title>
              <Button variant="ghost" onPress={applyMonday}>
                Aplicar horario de Lunes a toda la semana
              </Button>
            </Card.Header>
            <Card.Content className="flex flex-col gap-4">
              {days.map((day) => (
                <div key={day.id} className="grid items-end gap-3 sm:grid-cols-[8rem_1fr_1fr]">
                  <Checkbox
                    variant="secondary"
                    isSelected={day.active}
                    onChange={(active) =>
                      setDays((current) =>
                        current.map((item) => (item.id === day.id ? { ...item, active } : item)),
                      )
                    }
                  >
                    <Checkbox.Content>
                      <Checkbox.Control>
                        <Checkbox.Indicator />
                      </Checkbox.Control>
                      {day.label}
                    </Checkbox.Content>
                  </Checkbox>
                  <TimeField
                    aria-label={`Apertura ${day.label}`}
                    hourCycle={24}
                    granularity="minute"
                    isDisabled={!day.active}
                    value={clock(day.start)}
                    onChange={(value) =>
                      setDays((current) =>
                        current.map((item) =>
                          item.id === day.id
                            ? { ...item, start: formatClock(value, item.start) }
                            : item,
                        ),
                      )
                    }
                  >
                    <Label>Apertura</Label>
                    <TimeField.Group variant="secondary">
                      <TimeField.Input>
                        {(segment) => <TimeField.Segment segment={segment} />}
                      </TimeField.Input>
                    </TimeField.Group>
                  </TimeField>
                  <TimeField
                    aria-label={`Cierre ${day.label}`}
                    hourCycle={24}
                    granularity="minute"
                    isDisabled={!day.active}
                    value={clock(day.end)}
                    onChange={(value) =>
                      setDays((current) =>
                        current.map((item) =>
                          item.id === day.id
                            ? { ...item, end: formatClock(value, item.end) }
                            : item,
                        ),
                      )
                    }
                  >
                    <Label>Cierre</Label>
                    <TimeField.Group variant="secondary">
                      <TimeField.Input>
                        {(segment) => <TimeField.Segment segment={segment} />}
                      </TimeField.Input>
                    </TimeField.Group>
                  </TimeField>
                </div>
              ))}
            </Card.Content>
          </Card>
          <Card>
            <Card.Header>
              <Card.Title>Capacidad y cobro</Card.Title>
            </Card.Header>
            <Card.Content className="flex flex-col gap-6">
              <NumberField
                {...field}
                minValue={1}
                value={concurrent}
                onChange={(value) => setConcurrent(value)}
              >
                <Label>Eventos al mismo tiempo</Label>
                <NumberField.Group>
                  <NumberField.Input />
                </NumberField.Group>
                <Description>Cupo de eventos que puedes atender en el mismo bloque.</Description>
              </NumberField>
              <CheckboxGroup
                variant="secondary"
                value={payments}
                onChange={setPayments}
                className="grid gap-3 sm:grid-cols-2"
              >
                <Checkbox
                  value="cash"
                  variant="secondary"
                  className="rounded-xl border border-zinc-700 p-3 data-[selected=true]:border-accent"
                >
                  <Checkbox.Content>
                    <Checkbox.Control>
                      <Checkbox.Indicator />
                    </Checkbox.Control>
                    <span>
                      Efectivo
                      <span className="block text-sm text-zinc-400">
                        Pago contra entrega o en el evento
                      </span>
                    </span>
                  </Checkbox.Content>
                </Checkbox>
                <Checkbox
                  value="transfer"
                  variant="secondary"
                  className="rounded-xl border border-zinc-700 p-3 data-[selected=true]:border-accent"
                >
                  <Checkbox.Content>
                    <Checkbox.Control>
                      <Checkbox.Indicator />
                    </Checkbox.Control>
                    <span>
                      Transferencia
                      <span className="block text-sm text-zinc-400">Depósito interbancario SPEI</span>
                    </span>
                  </Checkbox.Content>
                </Checkbox>
              </CheckboxGroup>
              {payments.includes("transfer") ? (
                <TextField {...field} value={instructions} onChange={setInstructions}>
                  <Label>CLABE o instrucciones</Label>
                  <TextArea {...field} rows={2} />
                </TextField>
              ) : null}
            </Card.Content>
          </Card>
        </div>
      ) : null}

      <div className="flex justify-between">
        {step > 1 ? (
          <Button variant="outline" onPress={() => setStep((current) => current - 1)}>
            Atrás
          </Button>
        ) : (
          <span />
        )}
        {step < 3 ? (
          <Button variant="primary" onPress={() => setStep((current) => current + 1)}>
            Siguiente
          </Button>
        ) : (
          <Button variant="primary" isDisabled={busy} onPress={() => void finish()}>
            Terminar
          </Button>
        )}
      </div>
    </main>
  )
}
