import type { ReactNode } from "react"

type Tone = "success" | "warning" | "danger" | "info"

const TONE: Record<Tone, string> = {
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
  info: "bg-accent-soft text-accent",
}

export function KpiMetricCard({
  label,
  value,
  icon,
  tone = "warning",
  trend,
}: {
  label: string
  value: string
  icon: ReactNode
  tone?: Tone
  trend?: { direction: "up" | "down" | "flat"; label: string }
}) {
  const trendColor =
    trend?.direction === "down"
      ? "bg-danger-soft text-danger"
      : trend?.direction === "flat"
        ? "bg-background-tertiary text-zinc-300"
        : "bg-success-soft text-success"
  const arrow = trend?.direction === "down" ? "↘" : trend?.direction === "flat" ? "→" : "↗"
  return (
    <article className="rounded-2xl border border-zinc-800/80 bg-background-secondary p-5">
      <span className={`grid h-10 w-10 place-items-center rounded-xl ${TONE[tone]}`}>{icon}</span>
      <p className="mt-4 text-sm text-zinc-400">{label}</p>
      <div className="mt-2 flex items-end justify-between gap-3">
        <p className="text-3xl font-bold tracking-tight text-white tabular-nums">{value}</p>
        {trend ? (
          <span className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-1 text-sm font-medium ${trendColor}`}>
            {arrow} {trend.label}
          </span>
        ) : null}
      </div>
    </article>
  )
}
