import { useEffect, useRef, useState } from 'react'
import type { MeshItem } from '../api'
import { fileUrl } from '../api'
import { cx } from './ui'

declare module 'react' {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace JSX {
    interface IntrinsicElements {
      'model-viewer': React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement> & {
        src?: string
        alt?: string
        poster?: string
        'camera-controls'?: boolean
        'auto-rotate'?: boolean
        'shadow-intensity'?: string
        exposure?: string
        'interaction-prompt'?: string
        'environment-image'?: string
      }
    }
  }
}

/** Visor 3D real del GLB: girar, acercar y mover con el ratón. Muestra la
 *  versión pintada (textura horneada por Pixal3D) si existe, o la arcilla, que
 *  es la geometría exacta del STL. model-viewer se carga solo al usarlo. */
export function MeshViewer({ item }: { item: MeshItem }) {
  const [ready, setReady] = useState(false)
  const [clay, setClay] = useState(false)
  useEffect(() => {
    import('@google/model-viewer').then(() => setReady(true))
  }, [])
  const src = !clay && item.glb_color ? item.glb_color : item.glb
  // run3d.py exporta la arcilla con material blanco metálico: se pasa a gris mate
  const viewer = useRef<HTMLElement>(null)
  useEffect(() => {
    const mv = viewer.current as
      | (HTMLElement & { model?: { materials: { pbrMetallicRoughness: Record<string, (v: unknown) => void> }[] } })
      | null
    if (!mv || src !== item.glb) return
    const onLoad = () => {
      for (const m of mv.model?.materials ?? []) {
        m.pbrMetallicRoughness.setMetallicFactor(0)
        m.pbrMetallicRoughness.setRoughnessFactor(0.7)
        m.pbrMetallicRoughness.setBaseColorFactor([0.58, 0.57, 0.56, 1])
      }
    }
    mv.addEventListener('load', onLoad)
    return () => mv.removeEventListener('load', onLoad)
  }, [ready, src, item.glb])
  const poster = item.previews[0] ? fileUrl(item.previews[0]) : undefined
  if (!ready) {
    return poster ? <img src={poster} alt={item.name} className="h-full w-full object-contain" /> : null
  }
  return (
    <div className="relative h-full w-full">
      <model-viewer
        key={src}
        src={fileUrl(src)}
        alt={item.name}
        poster={poster}
        camera-controls
        auto-rotate
        shadow-intensity="1"
        exposure={src === item.glb ? '0.8' : '1'}
        environment-image="legacy"
        interaction-prompt="none"
        ref={viewer}
        style={{ width: '100%', height: '100%', background: 'transparent' }}
      />
      {item.glb_color && (
        <div
          role="radiogroup"
          aria-label="Acabado"
          className="absolute top-3 left-3 flex gap-1 rounded-[10px] border border-line bg-surface/90 p-1 backdrop-blur"
        >
          {[
            { value: false, label: 'Color' },
            { value: true, label: 'Arcilla' },
          ].map((o) => (
            <button
              key={o.label}
              type="button"
              role="radio"
              aria-checked={clay === o.value}
              onClick={() => setClay(o.value)}
              className={cx(
                'h-7 rounded-[7px] px-2.5 text-xs font-medium',
                clay === o.value ? 'bg-surface-2 text-fg' : 'text-muted hover:text-fg',
              )}
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
