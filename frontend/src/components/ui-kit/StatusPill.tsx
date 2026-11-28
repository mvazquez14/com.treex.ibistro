import type { ReactNode } from "react"

const DOT = {
  success: "bg-emerald-400",
  warning: "bg-amber-400",
  danger: "bg-rose-400",
  info: "bg-blue-400",
  default: "bg-zinc-400",
} as const

export function StatusPill({
  color = "default",
  children,
}: {
  color?: keyof typeof DOT
  children: ReactNode
}) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-zinc-800/80 px-2.5 py-1 text-sm text-zinc-100">
      <span className={`h-1.5 w-1.5 rounded-full ${DOT[color]}`} />
      {children}
    </span>
  )
}
