import { useCallback, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Modal } from './Modal'

export interface ConfirmRequest {
  title: string
  description: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  /** Destructive actions get the danger styling. Defaults to true. */
  danger?: boolean
  /** Runs when the user confirms. Throwing keeps the dialog open and shows the error. */
  onConfirm: () => void | Promise<void>
}

interface ConfirmDialogProps {
  open: boolean
  title: string
  description: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
  busy?: boolean
  error?: string | null
  onConfirm: () => void
  onCancel: () => void
}

/** In-app replacement for window.confirm. Cancel is the initially focused action. */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  danger = true,
  busy = false,
  error = null,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <Modal
      open={open}
      title={title}
      onClose={busy ? () => undefined : onCancel}
      className="modal--confirm"
      footer={
        <>
          <button type="button" className="btn btn--ghost" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </button>
          <button
            type="button"
            className={`btn ${danger ? 'btn--danger' : 'btn--primary'}`}
            onClick={onConfirm}
            disabled={busy}
            aria-busy={busy}
          >
            {busy ? 'Working…' : confirmLabel}
          </button>
        </>
      }
    >
      <div className="confirm__description">{description}</div>
      {error && (
        <p className="confirm__error" role="alert">
          {error}
        </p>
      )}
    </Modal>
  )
}

/**
 * State for one ConfirmDialog. Call `request(...)` from an event handler and render
 * `dialog` once in the component tree. Double submission is blocked while busy.
 */
export function useConfirmAction() {
  const [pending, setPending] = useState<ConfirmRequest | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const busyRef = useRef(false)

  const request = useCallback((next: ConfirmRequest) => {
    setError(null)
    setPending(next)
  }, [])

  const cancel = useCallback(() => {
    if (busyRef.current) return
    setPending(null)
    setError(null)
  }, [])

  const confirm = useCallback(async () => {
    if (!pending || busyRef.current) return
    busyRef.current = true
    setBusy(true)
    setError(null)
    try {
      await pending.onConfirm()
      setPending(null)
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : 'Something went wrong. Please try again.')
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }, [pending])

  const dialog = (
    <ConfirmDialog
      open={pending !== null}
      title={pending?.title ?? ''}
      description={pending?.description}
      confirmLabel={pending?.confirmLabel}
      cancelLabel={pending?.cancelLabel}
      danger={pending?.danger}
      busy={busy}
      error={error}
      onConfirm={confirm}
      onCancel={cancel}
    />
  )

  return { request, dialog }
}
