import { Dropdown, Label, Modal } from "@heroui/react"
import { useNavigate } from "@tanstack/react-router"
import { Ellipsis as MoreHorizontal } from "@gravity-ui/icons"
import { useState, type ReactNode } from "react"

import { Button } from "@/ui/controls"

export function RowActions({
  editTo,
  summary,
  onDelete,
  onView,
  onApprove,
}: {
  editTo: string
  summary: ReactNode
  onDelete: () => Promise<void>
  onView?: () => void
  onApprove?: () => void
}) {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [confirm, setConfirm] = useState(false)
  return (
    <div className="flex justify-end">
      <Dropdown>
        <Button isIconOnly size="sm" variant="light" aria-label="Acciones">
          <MoreHorizontal width={18} height={18} />
        </Button>
        <Dropdown.Popover>
          <Dropdown.Menu>
            <Dropdown.Item id="view" textValue="Ver detalle" onAction={() => (onView ? onView() : setOpen(true))}>
              <Label>Ver detalle</Label>
            </Dropdown.Item>
            {onApprove ? (
              <Dropdown.Item id="approve" textValue="Aprobar cotización" onAction={onApprove}>
                <Label>Aprobar cotización</Label>
              </Dropdown.Item>
            ) : null}
            <Dropdown.Item id="edit" textValue="Editar" onAction={() => void navigate({ to: editTo as never })}>
              <Label>Editar</Label>
            </Dropdown.Item>
            <Dropdown.Item id="delete" textValue="Eliminar" onAction={() => setConfirm(true)}>
              <Label>Eliminar</Label>
            </Dropdown.Item>
          </Dropdown.Menu>
        </Dropdown.Popover>
      </Dropdown>
      {onView ? null : <Modal.Backdrop isOpen={open} onOpenChange={setOpen}>
        <Modal.Container>
          <Modal.Dialog>
            <Modal.CloseTrigger />
            <Modal.Header>
              <Modal.Heading>Detalle</Modal.Heading>
            </Modal.Header>
            <Modal.Body>{summary}</Modal.Body>
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>}
      <Modal.Backdrop isOpen={confirm} onOpenChange={setConfirm}>
        <Modal.Container>
          <Modal.Dialog>
            <Modal.Header>
              <Modal.Heading>Eliminar registro</Modal.Heading>
            </Modal.Header>
            <Modal.Body>Esta acción no se puede deshacer.</Modal.Body>
            <Modal.Footer>
              <Button variant="light" onPress={() => setConfirm(false)}>
                Cancelar
              </Button>
              <Button
                color="danger"
                onPress={() => {
                  void onDelete().then(() => setConfirm(false))
                }}
              >
                Eliminar
              </Button>
            </Modal.Footer>
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>
    </div>
  )
}
