import { MagicWand } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import { api, fileUrl } from '../api'
import { useApp } from '../appContext'
import { ImageSource } from '../components/ImageSource'
import { Stage } from '../components/Stage'
import { TextArea, Toggle } from '../components/ui'
import { useElapsed, useJob } from '../useJob'
import { PresetSelects, usePresetChoice } from './presetChoice'
import { RunBar, useResults, Workbench } from './Workbench'

/** Proporción 'w / h' de la imagen de referencia: el resultado sale con la misma. */
function useImageAspect(path: string | null) {
  const [aspect, setAspect] = useState<string | undefined>()
  useEffect(() => {
    setAspect(undefined)
    if (!path) return
    const img = new Image()
    img.onload = () => setAspect(`${img.naturalWidth} / ${img.naturalHeight}`)
    img.src = fileUrl(path)
    return () => {
      img.onload = null
    }
  }, [path])
  return aspect
}

export function TransformPage() {
  const { inbox, lastGenerated, noteResult } = useApp()
  const results = useResults()
  const [isMap, setIsMap] = useState(false)
  const [reference, setReference] = useState<string | null>(null)
  const [extra, setExtra] = useState('')
  const preset = usePresetChoice()
  const [removeBg, setRemoveBg] = useState(false)
  const aspect = useImageAspect(reference)
  const job = useJob((item) => {
    results.add(item)
    if (item.kind === 'image') noteResult(item.path, item.path.startsWith('generated_transparent'))
  })
  const elapsed = useElapsed(!!job.active, job.since)

  const incoming = inbox.transformar
  useEffect(() => {
    if (incoming) setReference(incoming.path)
  }, [incoming])

  return (
    <Workbench
      controls={
        <>
          <ImageSource label="Imagen de referencia" value={reference} onChange={setReference} last={lastGenerated} />
          <Toggle
            checked={isMap}
            onChange={setIsMap}
            label="Es un mapa"
            hint="Usa el estilo de mapa de Ajustes en vez de una plantilla de estilo."
          />
          <PresetSelects isMap={isMap} withSpecies={!isMap} choice={preset} />
          {!isMap && (
            <p className="-mt-2 text-xs leading-relaxed text-muted">
              La anatomía rehace el cuerpo del personaje con el de la especie. Para objetos y fondos elige «Sin
              anatomía».
            </p>
          )}
          <TextArea
            label="Detalles adicionales"
            minRows={3}
            value={extra}
            placeholder="Opcional. Por ejemplo: que lleve la capa verde en vez de azul."
            onChange={(e) => setExtra(e.target.value)}
          />
          <div className="grid gap-2">
            <Toggle checked={removeBg} onChange={setRemoveBg} label="Quitar el fondo al terminar" />
          </div>
          <RunBar
            label="Transformar al estilo"
            icon={<MagicWand size={18} />}
            running={job.running}
            queued={job.queued + (job.active ? 1 : 0)}
            disabled={!reference}
            onRun={() =>
              reference &&
              job.start(() =>
                api.transform({
                  reference,
                  is_map: isMap,
                  extra,
                  style_id: preset.styleId,
                  species_id: isMap ? '' : preset.speciesId,
                  remove_bg: removeBg,
                }),
              )
            }
            error={job.error}
            warning={job.latest?.warning}
          />
        </>
      }
      stage={
        <Stage
          {...results}
          onSelect={results.setSelected}
          running={job.running}
          progress={job.progress}
          elapsed={elapsed}
          aspect={aspect}
          exclude="transformar"
          emptyTitle="Aquí aparecerá la versión redibujada"
          emptyHint="Sube una imagen y se redibuja con el estilo de tu mundo, conservando quién o qué es."
        />
      }
    />
  )
}
