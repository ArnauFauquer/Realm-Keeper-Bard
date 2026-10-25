import { Cube, Warning } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../appContext'
import { ImageSource } from '../components/ImageSource'
import { Stage } from '../components/Stage'
import { NumberInput, Select, TextArea } from '../components/ui'
import { useElapsed, useJob } from '../useJob'
import { RunBar, useResults, Workbench } from './Workbench'

export function MeshPage() {
  const { inbox, lastGenerated, lastTransparent, options, noteResult } = useApp()
  const results = useResults()
  const [source, setSource] = useState<string | null>(null)
  const [prepare, setPrepare] = useState('detailed')
  const [expression, setExpression] = useState('')
  const [height, setHeight] = useState(100)
  const [faces, setFaces] = useState(1000)
  const [variants, setVariants] = useState(1)
  const job = useJob((item) => {
    results.add(item)
    if (item.kind === 'image') noteResult(item.path, true)
  })
  const elapsed = useElapsed(!!job.active, job.since)

  const incoming = inbox.modelo_3d
  useEffect(() => {
    if (incoming) setSource(incoming.path)
  }, [incoming])

  const numbersOk = [height, faces, variants].every(Number.isFinite)
  const ready = options?.mesh_ready ?? true

  return (
    <Workbench
      controls={
        <>
          {!ready && (
            <div className="flex gap-2 rounded-[10px] border border-danger/35 bg-danger/8 p-3 text-xs text-danger">
              <Warning size={16} className="shrink-0" />
              Falta el entorno 3D: ejecuta models_3d\setup_3d.ps1.
            </div>
          )}
          <ImageSource
            label="Imagen"
            value={source}
            onChange={setSource}
            last={lastTransparent ?? lastGenerated}
            folders={['transparent', 'images', 'references']}
          />
          <Select
            label="Preparar con FLUX 3"
            value={prepare}
            onChange={setPrepare}
            options={options?.mesh_prepare_modes ?? []}
          />
          {prepare === 'detailed' && (
            <TextArea
              label="Expresión y notas del personaje"
              minRows={2}
              value={expression}
              placeholder="Opcional. Si lo dejas vacío, conserva la expresión de la imagen."
              onChange={(e) => setExpression(e.target.value)}
            />
          )}
          <div className="grid grid-cols-2 gap-3">
            <NumberInput label="Alto (mm)" value={height} onChange={setHeight} min={10} max={999} step={5} />
            <NumberInput label="Caras (miles)" value={faces} onChange={setFaces} min={50} max={3000} step={50} />
            <NumberInput label="Variantes" value={variants} onChange={setVariants} min={1} max={6} />
          </div>
          <p className="-mt-2 text-xs leading-relaxed text-muted">
            Cada variante usa una semilla aleatoria: son interpretaciones distintas de lo que no se ve en la imagen.
          </p>
          <RunBar
            label="Generar modelo 3D"
            icon={<Cube size={18} />}
            running={job.running}
            queued={job.queued + (job.active ? 1 : 0)}
            disabled={!source || !ready || !numbersOk}
            onRun={() =>
              source &&
              job.start(() =>
                api.mesh({
                  source,
                  prepare,
                  expression,
                  height_mm: height,
                  faces_k: Math.round(faces),
                  variants: Math.min(6, Math.max(1, Math.round(variants))),
                }),
              )
            }
            onCancel={job.cancel}
            error={job.error}
            warning={job.latest?.status === 'cancelled' ? 'Generación cancelada.' : undefined}
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
          exclude="modelo_3d"
          emptyTitle="Aquí aparecerá el modelo 3D"
          emptyHint="Funciona mejor con una imagen sin fondo de un solo personaje u objeto. Podrás girarlo con el ratón."
        />
      }
    />
  )
}
