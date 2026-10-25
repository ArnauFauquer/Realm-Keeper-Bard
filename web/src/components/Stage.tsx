import {
  ArrowSquareOut,
  Cube,
  DownloadSimple,
  FolderOpen,
  ImageSquare,
  MagicWand,
  Scissors,
} from '@phosphor-icons/react'
import { AnimatePresence, motion } from 'motion/react'
import type { ReactNode } from 'react'
import { api, fileUrl, thumbUrl, type ResultItem } from '../api'
import { useApp, type SendTarget } from '../appContext'
import { ImageViewer } from './ImageViewer'
import { MeshViewer } from './MeshViewer'
import { Button, cx, IconButton, Panel } from './ui'

const ASPECT: Record<string, string> = {
  personaje: '9 / 16',
  fondo: '16 / 9',
  objeto: '1 / 1',
  mapa: '3 / 2',
}

export function itemKey(item: ResultItem) {
  return item.kind === 'image' ? item.path : item.glb
}

function itemThumb(item: ResultItem) {
  if (item.kind === 'image') return thumbUrl(item.path, 200)
  return item.previews[0] ? thumbUrl(item.previews[0], 200) : null
}

const SEND_LABELS: Record<SendTarget, { label: string; icon: ReactNode }> = {
  transformar: { label: 'Transformar', icon: <MagicWand size={16} /> },
  quitar_fondo: { label: 'Quitar fondo', icon: <Scissors size={16} /> },
  modelo_3d: { label: 'Modelo 3D', icon: <Cube size={16} /> },
}

export function SendActions({ path, exclude, onSent }: { path: string; exclude?: SendTarget; onSent?: () => void }) {
  const { sendTo } = useApp()
  return (
    <>
      {(Object.keys(SEND_LABELS) as SendTarget[])
        .filter((t) => t !== exclude)
        .map((t) => (
          <Button key={t} variant="ghost" className="h-9 px-3" onClick={() => {
              sendTo(t, path)
              onSent?.()
            }}>
            {SEND_LABELS[t].icon}
            {SEND_LABELS[t].label}
          </Button>
        ))}
    </>
  )
}

function MeshFacts({ item }: { item: Extract<ResultItem, { kind: 'mesh' }> }) {
  const facts = [
    item.faces != null && `${item.faces.toLocaleString('es-ES')} caras`,
    item.size_mm && `${item.size_mm.map((v) => Math.round(v * 10) / 10).join(' × ')} mm`,
    item.watertight != null && (item.watertight ? 'Malla cerrada' : 'Malla con defectos menores'),
    item.filled && 'Maciza',
    item.seed != null && `Semilla ${item.seed}`,
    item.seconds != null && `${Math.round(item.seconds)} s`,
  ].filter(Boolean) as string[]
  if (!facts.length) return null
  return (
    <ul className="flex flex-wrap gap-1.5">
      {facts.map((f) => (
        <li key={f} className="rounded-full border border-line px-2.5 py-1 font-mono text-[11px] text-muted">
          {f}
        </li>
      ))}
    </ul>
  )
}

export function Stage({
  items,
  selected,
  onSelect,
  running,
  progress,
  elapsed,
  category,
  aspect,
  emptyTitle,
  emptyHint,
  exclude,
}: {
  items: ResultItem[]
  selected: ResultItem | null
  onSelect: (item: ResultItem) => void
  running: boolean
  progress: string
  elapsed: number
  category?: string
  /** Proporción del hueco de espera ('w / h'); si no, la de la categoría. */
  aspect?: string
  emptyTitle: string
  emptyHint: string
  exclude?: SendTarget
}) {
  return (
    <Panel className="flex min-h-[520px] min-w-0 flex-col overflow-hidden lg:h-full">
      <div className="flex min-h-14 flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-2">
        <p className="min-w-0 truncate font-mono text-xs text-muted">{selected ? selected.name : 'Sin resultado todavía'}</p>
        {selected && (
          <div className="flex flex-wrap items-center gap-1">
            {selected.kind === 'image' ? (
              <>
                <SendActions path={selected.path} exclude={exclude} />
                <span className="mx-1 h-5 w-px bg-line" />
                <IconButton label="Abrir con Windows" onClick={() => api.open(selected.path)}>
                  <ArrowSquareOut size={18} />
                </IconButton>
                <a
                  href={fileUrl(selected.path)}
                  download={selected.name}
                  aria-label="Descargar"
                  title="Descargar"
                  className="inline-flex size-9 items-center justify-center rounded-[10px] text-muted hover:bg-surface-2 hover:text-fg"
                >
                  <DownloadSimple size={18} />
                </a>
              </>
            ) : (
              <>
                {selected.stl && (
                  <Button variant="ghost" className="h-9 px-3" onClick={() => api.open(selected.stl!)}>
                    <ArrowSquareOut size={16} /> Abrir STL
                  </Button>
                )}
                <Button variant="ghost" className="h-9 px-3" onClick={() => api.open(selected.glb)}>
                  <ArrowSquareOut size={16} /> Abrir GLB
                </Button>
                <IconButton label="Abrir carpeta de modelos" onClick={() => api.open('generated_3d')}>
                  <FolderOpen size={18} />
                </IconButton>
              </>
            )}
          </div>
        )}
      </div>

      <div className="relative min-h-0 flex-1 p-3">
        <AnimatePresence mode="wait" initial={false}>
          {running && !selected ? (
            <motion.div
              key="running"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="grid h-full place-items-center"
            >
              <Pending ratio={aspect ?? ((category && ASPECT[category]) || '1 / 1')} progress={progress} elapsed={elapsed} />
            </motion.div>
          ) : selected ? (
            <motion.div
              key={itemKey(selected)}
              initial={{ opacity: 0, scale: 0.985 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
              className="h-full"
            >
              {selected.kind === 'image' ? (
                <ImageViewer src={fileUrl(selected.path)} alt={selected.name} />
              ) : (
                <div className="checker h-full overflow-hidden rounded-[10px]">
                  <MeshViewer item={selected} />
                </div>
              )}
            </motion.div>
          ) : (
            <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="grid h-full place-items-center">
              <div className="grid max-w-xs justify-items-center gap-3 text-center">
                <span className="grid size-14 place-items-center rounded-2xl border border-line bg-bg text-muted">
                  <ImageSquare size={26} />
                </span>
                <p className="text-sm font-medium text-fg">{emptyTitle}</p>
                <p className="text-xs leading-relaxed text-muted">{emptyHint}</p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        {running && selected && (
          <div className="absolute inset-x-6 top-6 flex justify-center">
            <ProgressPill progress={progress} elapsed={elapsed} />
          </div>
        )}
      </div>

      {selected?.kind === 'mesh' && (
        <div className="px-4 pb-3">
          <MeshFacts item={selected} />
        </div>
      )}

      {items.length > 0 && (
        <div className="border-t border-line px-3 py-3">
          <ul className="scroll-thin flex snap-x gap-2 overflow-x-auto pb-1">
            {[...items].reverse().map((item) => {
              const thumb = itemThumb(item)
              const active = selected && itemKey(selected) === itemKey(item)
              return (
                <li key={itemKey(item)} className="snap-start">
                  <button
                    type="button"
                    onClick={() => onSelect(item)}
                    title={item.name}
                    className={cx(
                      'checker relative block size-16 overflow-hidden rounded-[10px] border-2 transition-colors',
                      active ? 'border-accent' : 'border-transparent hover:border-line',
                    )}
                  >
                    {thumb ? (
                      <img src={thumb} alt={item.name} loading="lazy" className="h-full w-full object-contain" />
                    ) : (
                      <Cube size={22} className="m-auto text-muted" />
                    )}
                  </button>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </Panel>
  )
}

function ProgressPill({ progress, elapsed }: { progress: string; elapsed: number }) {
  return (
    <div className="flex max-w-full items-center gap-3 rounded-full border border-line bg-surface/95 px-4 py-2 text-xs shadow-panel backdrop-blur">
      <span className="relative flex size-2.5 shrink-0">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60 motion-reduce:animate-none" />
        <span className="relative inline-flex size-2.5 rounded-full bg-accent" />
      </span>
      <span className="truncate text-fg">{progress || 'Trabajando...'}</span>
      {elapsed > 0 && <span className="font-mono tabular-nums text-muted">{elapsed}s</span>}
    </div>
  )
}

function Pending({ ratio, progress, elapsed }: { ratio: string; progress: string; elapsed: number }) {
  const [w, h] = ratio.split('/').map(Number)
  return (
    <div className="flex h-full w-full flex-col items-center gap-4 py-2">
      {/* contenedor con unidades cq: el hueco cabe entero respetando la proporción */}
      <div className="flex min-h-0 w-full flex-1 items-center justify-center [container-type:size]">
        <div
          className="shimmer relative overflow-hidden rounded-[10px] bg-surface-2"
          style={{ width: `min(100cqw, ${(100 * w) / h}cqh)`, aspectRatio: ratio }}
        />
      </div>
      <ProgressPill progress={progress} elapsed={elapsed} />
    </div>
  )
}
