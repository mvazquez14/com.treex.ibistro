import {
  Avatar as HeroAvatar,
  Button as HeroButton,
  Card as HeroCard,
  Chip as HeroChip,
  Input as HeroInput,
  Label,
  ListBox,
  Select as HeroSelect,
  Switch as HeroSwitch,
  TextArea,
} from "@heroui/react"
import { Link } from "@tanstack/react-router"
import type { KeyboardEvent, ReactNode } from "react"

import { cn } from "@/lib/utils"

type ButtonProps = {
  children?: ReactNode
  onPress?: () => void
  isIconOnly?: boolean
  variant?: "solid" | "bordered" | "light" | "flat"
  color?: "primary" | "danger" | "default"
  size?: "sm" | "md" | "lg"
  isLoading?: boolean
  startContent?: ReactNode
  to?: string
  params?: Record<string, string>
  href?: string
  target?: string
  rel?: string
  className?: string
  "aria-label"?: string
}

export function Button({
  children,
  onPress,
  isIconOnly,
  variant,
  color,
  size,
  isLoading,
  startContent,
  to,
  params,
  href,
  target,
  rel,
  className,
  ...rest
}: ButtonProps) {
  const tone =
    color === "danger"
      ? "danger"
      : color === "primary" || variant === "solid" || variant === undefined
        ? "primary"
        : variant === "bordered"
          ? "outline"
          : variant === "light"
            ? "ghost"
            : "secondary"
  if (to) {
    const quiet = variant === "flat" || variant === "light" || variant === "bordered"
    return (
      <Link
        to={to as never}
        params={params as never}
        aria-label={rest["aria-label"]}
        className={cn(
          quiet
            ? "inline-flex items-center gap-2 rounded-lg border border-zinc-700 px-3 py-2 text-base text-zinc-100"
            : "inline-flex items-center gap-2 rounded-full bg-accent px-6 py-2 text-base font-semibold text-accent-foreground",
          className,
        )}
      >
        {startContent}
        {children}
      </Link>
    )
  }
  if (href) {
    return (
      <a
        href={href}
        target={target}
        rel={rel}
        className="inline-flex items-center rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-accent-foreground"
      >
        {children}
      </a>
    )
  }
  return (
    <HeroButton
      aria-label={rest["aria-label"]}
      variant={tone}
      size={size === "sm" ? "sm" : size === "lg" ? "lg" : "md"}
      isIconOnly={isIconOnly}
      isDisabled={isLoading}
      className={className}
      onPress={onPress}
    >
      {startContent}
      {children}
    </HeroButton>
  )
}

export function Input({
  label,
  hideLabel,
  value,
  onValueChange,
  type,
  min,
  className,
  placeholder,
  startContent,
  onKeyDown,
}: {
  label?: string
  hideLabel?: boolean
  value?: string
  onValueChange?: (value: string) => void
  type?: string
  min?: number
  className?: string
  placeholder?: string
  isClearable?: boolean
  startContent?: ReactNode
  labelPlacement?: string
  variant?: string
  onKeyDown?: (event: KeyboardEvent<HTMLInputElement>) => void
}) {
  return (
    <label className={hideLabel ? (className ?? "block") : `flex flex-col gap-2 ${className ?? ""}`}>
      {!hideLabel && label ? <span className="text-sm font-medium text-zinc-200">{label}</span> : null}
      <span className="flex items-center gap-2">
        {startContent}
        <HeroInput
          aria-label={label || placeholder || "Campo"}
          className="w-full text-base"
          fullWidth
          variant="secondary"
          value={value}
          placeholder={placeholder}
          type={type}
          min={min}
          onChange={(event) => onValueChange?.(event.target.value)}
          onKeyDown={onKeyDown}
        />
      </span>
    </label>
  )
}

export function Select({
  label,
  hideLabel,
  selectedKeys,
  onChange,
  children,
  className,
  ariaLabel,
}: {
  label?: string
  hideLabel?: boolean
  selectedKeys?: string[]
  onChange?: (event: { target: { value: string } }) => void
  children: ReactNode
  className?: string
  variant?: string
  size?: string
  labelPlacement?: string
  "aria-label"?: string
  ariaLabel?: string
}) {
  return (
    <HeroSelect
      className={`w-full text-base ${className ?? ""}`}
      variant="secondary"
      aria-label={ariaLabel || label || "Elegir"}
      selectedKey={selectedKeys?.[0] ?? null}
      onSelectionChange={(key) => onChange?.({ target: { value: String(key ?? "") } })}
      placeholder={hideLabel ? "Elegir" : label || "Elegir"}
    >
      {!hideLabel && label ? <Label className="text-sm font-medium text-zinc-200">{label}</Label> : null}
      <HeroSelect.Trigger>
        <HeroSelect.Value />
        <HeroSelect.Indicator />
      </HeroSelect.Trigger>
      <HeroSelect.Popover>
        <ListBox>{children}</ListBox>
      </HeroSelect.Popover>
    </HeroSelect>
  )
}

export function SelectItem({ id, children }: { id: string; children: ReactNode }) {
  const text = typeof children === "string" ? children : id
  return (
    <ListBox.Item id={id} textValue={text}>
      {children}
    </ListBox.Item>
  )
}

export function Switch({
  isSelected,
  onValueChange,
  children,
  size,
}: {
  isSelected?: boolean
  onValueChange?: (value: boolean) => void
  children?: ReactNode
  size?: string
  color?: string
}) {
  return (
    <HeroSwitch isSelected={isSelected} onChange={onValueChange} size={size === "sm" ? "sm" : "md"}>
      <HeroSwitch.Content>
        <HeroSwitch.Control>
          <HeroSwitch.Thumb />
        </HeroSwitch.Control>
        {children}
      </HeroSwitch.Content>
    </HeroSwitch>
  )
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <HeroCard className={className}>{children}</HeroCard>
}

export function CardBody({ children, className }: { children: ReactNode; className?: string }) {
  return <HeroCard.Content className={`grid gap-3 ${className ?? ""}`}>{children}</HeroCard.Content>
}

export function Textarea({
  label,
  hideLabel,
  value,
  onValueChange,
  className,
}: {
  label?: string
  hideLabel?: boolean
  value?: string
  onValueChange?: (value: string) => void
  className?: string
  labelPlacement?: string
  variant?: string
}) {
  return (
    <label className={hideLabel ? (className ?? "block") : `flex flex-col gap-2 ${className ?? ""}`}>
      {!hideLabel && label ? <span className="text-sm font-medium text-zinc-200">{label}</span> : null}
      <TextArea
        aria-label={label || "Texto"}
        className="w-full text-base"
        fullWidth
        variant="secondary"
        value={value}
        onChange={(event) => onValueChange?.(event.target.value)}
      />
    </label>
  )
}

export function Chip({
  children,
  variant,
  color,
  size,
}: {
  children: ReactNode
  variant?: string
  color?: "success" | "warning" | "danger" | "accent" | "default"
  size?: "sm" | "md" | "lg"
}) {
  const tone = variant === "flat" || variant === "soft" ? "soft" : undefined
  return (
    <HeroChip color={color} size={size} variant={tone}>
      {children}
    </HeroChip>
  )
}

export function Avatar({ src, name, className }: { src?: string; name?: string; className?: string }) {
  return (
    <HeroAvatar className={className}>
      {src ? <HeroAvatar.Image src={src} alt={name || ""} /> : null}
      <HeroAvatar.Fallback>{name?.slice(0, 1) || "i"}</HeroAvatar.Fallback>
    </HeroAvatar>
  )
}
