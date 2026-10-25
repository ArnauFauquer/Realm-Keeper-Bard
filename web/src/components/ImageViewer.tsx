import { CornersOut, MagnifyingGlassMinus, MagnifyingGlassPlus } from '@phosphor-icons/react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { IconButton } from './ui'

const MIN = 0.05
const MAX = 8

/** Visor con zoom (rueda, centrado en el cursor) y desplazamiento (arrastrar),
 *  para revisar el detalle de las imágenes a resolución completa. La posición
 *  se escribe directamente en el estilo: solo el % de zoom pasa por React. */
export function ImageViewer({ src, alt }: { src: string; alt: string }) {
  const box = useRef<HTMLDivElement>(null)
  const img = useRef<HTMLImageElement>(null)
  const t = useRef({ s: 1, x: 0, y: 0 })
  const drag = useRef<{ x: number; y: number } | null>(null)
  const [zoom, setZoom] = useState(1)

  const apply = useCallback(() => {
    const { s, x, y } = t.current
    if (img.current) img.current.style.transform = `translate(${x}px, ${y}px) scale(${s})`
    setZoom(s)
  }, [])

  const fit = useCallback(() => {
    const el = img.current
    const b = box.current
    if (!el || !b || !el.naturalWidth) return
    const pad = 24
    const s = Math.min((b.clientWidth - pad) / el.naturalWidth, (b.clientHeight - pad) / el.naturalHeight, 1)
    t.current = {
      s,
      x: (b.clientWidth - el.naturalWidth * s) / 2,
      y: (b.clientHeight - el.naturalHeight * s) / 2,
    }
    apply()
  }, [apply])

  const zoomAt = useCallback(
    (factor: number, cx?: number, cy?: number) => {
      const b = box.current
      if (!b) return
      const { s, x, y } = t.current
      const ns = Math.min(MAX, Math.max(MIN, s * factor))
      const px = cx ?? b.clientWidth / 2
      const py = cy ?? b.clientHeight / 2
      t.current = { s: ns, x: px - ((px - x) * ns) / s, y: py - ((py - y) * ns) / s }
      apply()
    },
    [apply],
  )

  useEffect(() => {
    const b = box.current
    if (!b) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const r = b.getBoundingClientRect()
      zoomAt(e.deltaY < 0 ? 1.12 : 1 / 1.12, e.clientX - r.left, e.clientY - r.top)
    }
    b.addEventListener('wheel', onWheel, { passive: false })
    const ro = new ResizeObserver(() => fit())
    ro.observe(b)
    return () => {
      b.removeEventListener('wheel', onWheel)
      ro.disconnect()
    }
  }, [fit, zoomAt])

  return (
    <div className="relative h-full w-full">
      <div
        ref={box}
        className="checker relative h-full w-full cursor-grab touch-none overflow-hidden rounded-[10px] active:cursor-grabbing"
        onPointerDown={(e) => {
          drag.current = { x: e.clientX - t.current.x, y: e.clientY - t.current.y }
          e.currentTarget.setPointerCapture(e.pointerId)
        }}
        onPointerMove={(e) => {
          if (!drag.current) return
          t.current.x = e.clientX - drag.current.x
          t.current.y = e.clientY - drag.current.y
          if (img.current) {
            img.current.style.transform = `translate(${t.current.x}px, ${t.current.y}px) scale(${t.current.s})`
          }
        }}
        onPointerUp={() => (drag.current = null)}
        onDoubleClick={(e) => {
          if (t.current.s < 0.99) {
            const r = e.currentTarget.getBoundingClientRect()
            zoomAt(1 / t.current.s, e.clientX - r.left, e.clientY - r.top)
          } else fit()
        }}
      >
        <img
          ref={img}
          src={src}
          alt={alt}
          draggable={false}
          onLoad={fit}
          className="absolute left-0 top-0 max-w-none origin-top-left select-none"
        />
      </div>
      <div className="absolute bottom-3 left-3 flex items-center gap-0.5 rounded-full border border-line bg-surface/90 px-1 py-0.5 backdrop-blur">
        <IconButton label="Alejar" onClick={() => zoomAt(1 / 1.25)} className="size-8 rounded-full">
          <MagnifyingGlassMinus size={16} />
        </IconButton>
        <span className="w-12 text-center font-mono text-xs tabular-nums text-muted">{Math.round(zoom * 100)}%</span>
        <IconButton label="Acercar" onClick={() => zoomAt(1.25)} className="size-8 rounded-full">
          <MagnifyingGlassPlus size={16} />
        </IconButton>
        <IconButton label="Ajustar a la vista" onClick={fit} className="size-8 rounded-full">
          <CornersOut size={16} />
        </IconButton>
      </div>
    </div>
  )
}
