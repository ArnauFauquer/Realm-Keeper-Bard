import { useEffect, useRef, useState } from 'react'
import type { MeshItem } from '../api'
import { fileUrl } from '../api'

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

/** Visor 3D real del GLB (el que exporta run3d.py, sin textura): girar,
 *  acercar y mover con el ratón. model-viewer se carga solo al usarlo. */
export function MeshViewer({ item }: { item: MeshItem }) {
  const [ready, setReady] = useState(false)
  useEffect(() => {
    import('@google/model-viewer').then(() => setReady(true))
  }, [])
  // run3d.py exporta un material blanco metálico: se pasa a arcilla gris mate
  const viewer = useRef<HTMLElement>(null)
  useEffect(() => {
    const mv = viewer.current as
      | (HTMLElement & { model?: { materials: { pbrMetallicRoughness: Record<string, (v: unknown) => void> }[] } })
      | null
    if (!mv) return
    const onLoad = () => {
      for (const m of mv.model?.materials ?? []) {
        m.pbrMetallicRoughness.setMetallicFactor(0)
        m.pbrMetallicRoughness.setRoughnessFactor(0.7)
        m.pbrMetallicRoughness.setBaseColorFactor([0.58, 0.57, 0.56, 1])
      }
    }
    mv.addEventListener('load', onLoad)
    return () => mv.removeEventListener('load', onLoad)
  }, [ready, item.glb])
  const poster = item.previews[0] ? fileUrl(item.previews[0]) : undefined
  if (!ready) {
    return poster ? <img src={poster} alt={item.name} className="h-full w-full object-contain" /> : null
  }
  return (
    <model-viewer
      key={item.glb}
      src={fileUrl(item.glb)}
      alt={item.name}
      poster={poster}
      camera-controls
      auto-rotate
      shadow-intensity="1"
      exposure="0.8"
      environment-image="legacy"
      interaction-prompt="none"
      ref={viewer}
      style={{ width: '100%', height: '100%', background: 'transparent' }}
    />
  )
}
