export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export type Session = {
  authenticated: boolean
  email?: string
  business_name?: string
  slug?: string | null
  has_active_plan?: boolean
  billing_url?: string
  logout_url?: string
  public_base_url?: string
  impersonating?: string | null
  is_superuser?: boolean
  onboarding_completed?: boolean
}

type Json = Record<string, unknown> | unknown[] | undefined

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (init?.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }
  const response = await fetch(path, { ...init, credentials: "include", headers })
  if (response.status === 401 && path.startsWith("/api/v1")) {
    window.location.href = "/login"
  }
  if (!response.ok) {
    let detail = "No se pudo completar la acción"
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === "string") detail = body.detail
    } catch {
      detail = response.statusText || detail
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export function api<T>(path: string, init?: RequestInit): Promise<T> {
  return request<T>(`/api/v1${path}`, init)
}

export async function getSession(): Promise<Session> {
  const response = await fetch("/api/auth/session", { credentials: "include" })
  if (response.status === 401) return { authenticated: false }
  if (!response.ok) {
    throw new ApiError(response.status, "No se pudo leer la sesión")
  }
  return (await response.json()) as Session
}

export function money(value: string | number | null | undefined): string {
  const amount = Number(value ?? 0)
  return amount.toLocaleString("es-MX", { style: "currency", currency: "MXN" })
}

export function jsonBody(body: Json): RequestInit {
  return { method: "POST", body: JSON.stringify(body ?? {}) }
}

export function patchBody(body: Json): RequestInit {
  return { method: "PATCH", body: JSON.stringify(body ?? {}) }
}
