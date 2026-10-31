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

  const incoming = inbox.model_3d
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
              The 3D environment is missing: run models_3d\setup_3d.ps1.
            </div>
          )}
          <ImageSource
            label="Image"
            value={source}
            onChange={setSource}
            last={lastTransparent ?? lastGenerated}
            folders={['transparent', 'images', 'references']}
          />
          <Select
            label="Prepare with FLUX 3"
            value={prepare}
            onChange={setPrepare}
            options={options?.mesh_prepare_modes ?? []}
          />
          {prepare === 'detailed' && (
            <TextArea
              label="Character expression and notes"
              minRows={2}
              value={expression}
              placeholder="Optional. If left empty, the expression in the image is kept."
              onChange={(e) => setExpression(e.target.value)}
            />
          )}
          <div className="grid grid-cols-2 gap-3">
            <NumberInput label="Height (mm)" value={height} onChange={setHeight} min={10} max={999} step={5} />
            <NumberInput label="Faces (thousands)" value={faces} onChange={setFaces} min={50} max={3000} step={50} />
            <NumberInput label="Variants" value={variants} onChange={setVariants} min={1} max={6} />
          </div>
          <p className="-mt-2 text-xs leading-relaxed text-muted">
            Each variant uses a random seed: they are different interpretations of whatever the image does not show.
          </p>
          <RunBar
            label="Generate 3D model"
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
            warning={job.latest?.status === 'cancelled' ? 'Generation cancelled.' : undefined}
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
          exclude="model_3d"
          emptyTitle="Your 3D model will appear here"
          emptyHint="Works best with a background-free image of a single character or object. You can rotate it with the mouse."
        />
      }
    />
  )
}
