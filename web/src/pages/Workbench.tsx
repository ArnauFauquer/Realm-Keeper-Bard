import { Queue, Stop, Warning } from '@phosphor-icons/react'
import type { ReactNode } from 'react'
import { useCallback, useState } from 'react'
import type { ResultItem } from '../api'
import { Button, Panel } from '../components/ui'

/** Resultados de la sesión de una página: el último queda seleccionado. */
export function useResults() {
  const [items, setItems] = useState<ResultItem[]>([])
  const [selected, setSelected] = useState<ResultItem | null>(null)
  const add = useCallback((item: ResultItem) => {
    setItems((prev) => [...prev, item])
    setSelected(item)
  }, [])
  return { items, selected, setSelected, add }
}

/** Columna de controles + escenario de resultado; en móvil se apilan. */
export function Workbench({ controls, stage }: { controls: ReactNode; stage: ReactNode }) {
  return (
    <div className="grid gap-5 lg:h-[calc(100dvh-10.5rem)] lg:grid-cols-[minmax(340px,400px)_minmax(0,1fr)]">
      <Panel className="scroll-thin min-h-0 overflow-y-auto">
        <div className="grid gap-5 p-5">{controls}</div>
      </Panel>
      {stage}
    </div>
  )
}

export function RunBar({
  label,
  icon,
  running,
  queued = 0,
  disabled,
  onRun,
  onCancel,
  error,
  warning,
}: {
  label: string
  icon: ReactNode
  /** Hay trabajos de esta página en marcha o en cola: el botón sigue activo y encola otro. */
  running: boolean
  queued?: number
  disabled?: boolean
  onRun: () => void
  onCancel?: () => void
  error?: string
  warning?: string
}) {
  return (
    <div className="sticky bottom-0 -mx-5 -mb-5 grid gap-3 border-t border-line bg-surface/95 px-5 py-4 backdrop-blur">
      <div className="flex gap-2">
        <Button variant="primary" className="h-11 flex-1" disabled={disabled} onClick={onRun}>
          {running ? <Queue size={18} /> : icon}
          {running ? 'Añadir a la cola' : label}
        </Button>
        {onCancel && running && (
          <Button variant="danger" className="h-11" onClick={onCancel} title="Cancela el que está en marcha">
            <Stop size={16} weight="fill" /> Cancelar
          </Button>
        )}
      </div>
      {running && queued > 0 && (
        <p className="text-xs text-muted">
          {queued === 1 ? '1 trabajo de esta sección' : `${queued} trabajos de esta sección`} en la cola. Puedes seguir
          cambiando los ajustes y encolar más.
        </p>
      )}
      {error && (
        <div role="alert" className="flex gap-2 rounded-[10px] border border-danger/35 bg-danger/8 p-3 text-xs text-danger">
          <Warning size={16} className="mt-px shrink-0" />
          <pre className="scroll-thin max-h-40 overflow-auto whitespace-pre-wrap font-sans leading-relaxed">{error}</pre>
        </div>
      )}
      {warning && !error && <p className="text-xs text-muted">{warning}</p>}
    </div>
  )
}
