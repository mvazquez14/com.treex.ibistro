import { ArrowDownToLine, Magnifier, Plus } from "@gravity-ui/icons"
import { Table } from "@heroui/react"
import { useMemo, useState, type ReactNode } from "react"

import { BreadcrumbBar } from "@/components/master/EditorLayout"
import { Button, Input, Select, SelectItem } from "@/ui/controls"

export type DataColumn<T> = {
  key: string
  label: string
  render: (row: T) => ReactNode
  exportValue?: (row: T) => string
  className?: string
}

export function DataTableCard<T extends { id: string }>({
  crumbs,
  title,
  description,
  rows,
  columns,
  searchText,
  createTo,
  createLabel,
  extra,
  boxed = true,
  frameClassName,
}: {
  crumbs: string[]
  title: string
  description?: string
  rows: T[]
  columns: DataColumn<T>[]
  searchText: (row: T) => string
  createTo?: string
  createLabel?: string
  extra?: ReactNode
  boxed?: boolean
  frameClassName?: string
}) {
  const [query, setQuery] = useState("")
  const [pageSize, setPageSize] = useState("10")
  const [page, setPage] = useState(1)
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return rows
    return rows.filter((row) => searchText(row).toLowerCase().includes(needle))
  }, [query, rows, searchText])
  const size = Number(pageSize)
  const pages = Math.max(1, Math.ceil(filtered.length / size))
  const current = Math.min(page, pages)
  const start = (current - 1) * size
  const visible = filtered.slice(start, start + size)
  const from = filtered.length === 0 ? 0 : start + 1
  const to = Math.min(start + size, filtered.length)
  const windowStart = Math.max(1, Math.min(current - 3, pages - 6))
  const pageNumbers = Array.from({ length: Math.min(pages, 7) }, (_, index) => windowStart + index).filter(
    (item) => item >= 1 && item <= pages,
  )

  function exportCsv() {
    const header = columns.map((column) => column.label).join(",")
    const body = filtered
      .map((row) =>
        columns.map((column) => `"${(column.exportValue?.(row) ?? "").replace(/"/g, '""')}"`).join(","),
      )
      .join("\n")
    const blob = new Blob([`${header}\n${body}`], { type: "text/csv;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = `${title}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className={frameClassName ?? (boxed ? "mx-auto w-full max-w-7xl space-y-6 px-4 py-8 sm:px-6 lg:px-8" : "flex flex-col gap-6")}>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <BreadcrumbBar crumbs={crumbs} />
          <h1 className="text-5xl font-bold leading-none text-white">{title}</h1>
          {description ? <p className="mt-1 max-w-2xl text-base text-zinc-400">{description}</p> : null}
        </div>
        {createTo && createLabel ? (
          <Button to={createTo} color="primary" className="rounded-full bg-accent px-6 font-semibold text-accent-foreground" startContent={<Plus width={16} height={16} />}>
            {createLabel}
          </Button>
        ) : null}
      </div>
      <div className="rounded-2xl border border-zinc-800/80 bg-background-secondary p-4 sm:p-6">
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
          <Input
            label="Buscar"
            hideLabel
            placeholder="Buscar"
            startContent={<Magnifier width={16} height={16} />}
            value={query}
            onValueChange={(value) => {
              setQuery(value)
              setPage(1)
            }}
            className="w-full sm:w-[30%]"
          />
          <div className="flex flex-wrap items-center gap-3 sm:ml-auto">
          <Select
            ariaLabel="Registros por página"
            hideLabel
            label="Registros"
            selectedKeys={[pageSize]}
            onChange={(event) => {
              setPageSize(event.target.value)
              setPage(1)
            }}
            className="w-full sm:w-28"
          >
            {["10", "25", "50"].map((item) => (
              <SelectItem id={item} key={item}>
                {item}
              </SelectItem>
            ))}
          </Select>
          {extra}
          <Button variant="flat" startContent={<ArrowDownToLine width={16} height={16} />} onPress={exportCsv}>
            Exportar
          </Button>
          </div>
        </div>
        {visible.length === 0 ? (
          <p className="py-8 text-base text-zinc-400">No hay registros con ese filtro.</p>
        ) : (
          <Table>
            <Table.ScrollContainer>
              <Table.Content aria-label={title}>
                <Table.Header className="bg-background-tertiary">
                  {columns.map((column) => (
                    <Table.Column
                      key={column.key}
                      isRowHeader={column.key === "name" || column.key === "index"}
                      className={`bg-background-tertiary text-sm font-medium normal-case text-zinc-400 ${column.className ?? ""}`}
                    >
                      {column.label}
                    </Table.Column>
                  ))}
                </Table.Header>
                <Table.Body>
                  {visible.map((row, index) => (
                    <Table.Row key={row.id} id={row.id} className="border-b border-zinc-800/70">
                      {columns.map((column) => (
                        <Table.Cell key={column.key} className={`py-4 text-base ${column.className ?? ""}`}>
                          {column.key === "index" ? start + index + 1 : column.render(row)}
                        </Table.Cell>
                      ))}
                    </Table.Row>
                  ))}
                </Table.Body>
              </Table.Content>
            </Table.ScrollContainer>
          </Table>
        )}
        <div className="mt-4 flex flex-col gap-3 border-t border-zinc-800/80 pt-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-zinc-400">
            Mostrando {from}–{to} de {filtered.length}
          </p>
          <div className="flex flex-wrap gap-1">
            {pageNumbers.map((item) => (
              <button
                key={item}
                type="button"
                className={`grid h-9 min-w-9 place-items-center rounded-lg px-2 text-sm font-medium ${
                  item === current ? "bg-accent text-accent-foreground" : "text-zinc-300 hover:bg-background-tertiary"
                }`}
                onClick={() => setPage(item)}
              >
                {item}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
