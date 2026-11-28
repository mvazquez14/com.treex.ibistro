import { Button, Card } from "@heroui/react"
import { useEffect, useState } from "react"

const MAX_BYTES = 5 * 1024 * 1024
const ALLOWED = new Set(["image/png", "image/jpeg", "image/webp"])

type LogoDropZoneProps = {
  file: File | null
  onFile: (file: File | null) => void
  inputId?: string
  heading?: string
  previewUrl?: string | null
  presentation?: "card" | "inline"
}

function formatWeight(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function LogoDropZone({
  file,
  onFile,
  inputId = "logo-file",
  heading = "Suelta el logo aquí",
  previewUrl = null,
  presentation = "card",
}: LogoDropZoneProps) {
  const [message, setMessage] = useState("")
  const [preview, setPreview] = useState<string | null>(null)

  useEffect(() => {
    if (!file) {
      setPreview(previewUrl)
      return
    }
    const url = URL.createObjectURL(file)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file, previewUrl])

  function take(next: File | undefined) {
    if (!next) return
    if (!ALLOWED.has(next.type)) {
      setMessage("La imagen debe ser PNG, JPG o WEBP.")
      return
    }
    if (next.size > MAX_BYTES) {
      setMessage("La imagen no puede pesar más de 5 MB.")
      return
    }
    setMessage("")
    onFile(next)
  }

  if (presentation === "inline") {
    return (
      <div
        className="flex flex-col gap-4 rounded-2xl border border-dashed border-zinc-700 bg-zinc-800/40 p-4 sm:flex-row sm:items-center"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault()
          take(event.dataTransfer.files[0])
        }}
      >
        {preview ? (
          <img alt="Vista previa" className="size-20 rounded-2xl object-cover" src={preview} />
        ) : (
          <div className="grid size-20 place-items-center rounded-2xl bg-zinc-800 text-sm text-zinc-400">
            Foto
          </div>
        )}
        <div className="min-w-0">
          <p className="text-sm text-zinc-400">PNG, JPG o WEBP, máximo 5 MB</p>
          {file ? (
            <p className="mt-1 truncate text-sm text-zinc-200">
              {file.name} · {formatWeight(file.size)}
            </p>
          ) : null}
          {message ? <p className="mt-1 text-sm text-red-400">{message}</p> : null}
          <p className="mt-2 text-sm">
            <button
              type="button"
              className="font-medium text-accent"
              onClick={() => document.getElementById(inputId)?.click()}
            >
              Clic para cambiar imagen
            </button>
            <span className="mx-2 text-zinc-500">-</span>
            <button type="button" className="text-zinc-300" onClick={() => onFile(null)}>
              Restablecer
            </button>
          </p>
        </div>
        <input
          id={inputId}
          className="sr-only"
          type="file"
          accept="image/png,image/jpeg,image/webp"
          onChange={(event) => take(event.target.files?.[0])}
        />
      </div>
    )
  }

  return (
    <Card className="border border-dashed border-zinc-600 bg-transparent">
      <Card.Content className="flex flex-col items-center gap-4 p-6 text-center">
        {preview ? (
          <img
            alt="Vista previa del logo"
            className="size-24 rounded-2xl object-cover"
            src={preview}
          />
        ) : (
          <div className="flex size-24 items-center justify-center rounded-2xl bg-[#27272A] text-sm text-zinc-400">
            Logo
          </div>
        )}
        <div>
          <p className="font-semibold text-accent">{heading}</p>
          <p className="mt-1 text-sm text-zinc-400">PNG, JPG o WEBP, máximo 5 MB</p>
        </div>
        {file ? (
          <p className="text-sm text-zinc-300">
            {file.name} · {formatWeight(file.size)}
          </p>
        ) : null}
        {message ? <p className="text-sm text-red-400">{message}</p> : null}
        <div className="flex gap-2">
          <Button variant="secondary" onPress={() => document.getElementById(inputId)?.click()}>
            {file ? "Cambiar imagen" : "Elegir imagen"}
          </Button>
          {file ? (
            <Button variant="outline" onPress={() => onFile(null)}>
              Quitar
            </Button>
          ) : null}
        </div>
        <input
          id={inputId}
          className="sr-only"
          type="file"
          accept="image/png,image/jpeg,image/webp"
          onChange={(event) => take(event.target.files?.[0])}
        />
        <div
          className="w-full rounded-xl border border-zinc-700 px-3 py-6 text-sm text-zinc-400"
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault()
            take(event.dataTransfer.files[0])
          }}
        >
          O arrastra el archivo a esta zona
        </div>
      </Card.Content>
    </Card>
  )
}
