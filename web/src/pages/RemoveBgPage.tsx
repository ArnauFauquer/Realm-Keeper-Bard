import { Scissors } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../appContext'
import { ImageSource } from '../components/ImageSource'
import { Stage } from '../components/Stage'
import { useElapsed, useJob } from '../useJob'
import { RunBar, useResults, Workbench } from './Workbench'

export function RemoveBgPage() {
  const { inbox, lastGenerated, noteResult } = useApp()
  const results = useResults()
  const [source, setSource] = useState<string | null>(null)
  const job = useJob((item) => {
    results.add(item)
    if (item.kind === 'image') noteResult(item.path, true)
  })
  const elapsed = useElapsed(!!job.active, job.since)

  const incoming = inbox.quitar_fondo
  useEffect(() => {
    if (incoming) setSource(incoming.path)
  }, [incoming])

  return (
    <Workbench
      controls={
        <>
          <ImageSource label="Imagen" value={source} onChange={setSource} last={lastGenerated} />
          <p className="text-xs leading-relaxed text-muted">
            Funciona mejor con personajes y objetos sobre fondo liso, que es como salen de Crear.
          </p>
          <RunBar
            label="Quitar fondo"
            icon={<Scissors size={18} />}
            running={job.running}
            queued={job.queued + (job.active ? 1 : 0)}
            disabled={!source}
            onRun={() => source && job.start(() => api.removeBg(source))}
            error={job.error}
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
          exclude="quitar_fondo"
          emptyTitle="Aquí aparecerá el PNG transparente"
          emptyHint="Se guarda en generated_transparent, listo para usarlo como asset o pasarlo a Modelo 3D."
        />
      }
    />
  )
}
