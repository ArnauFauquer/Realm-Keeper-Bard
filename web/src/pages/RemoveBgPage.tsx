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

  const incoming = inbox.remove_bg
  useEffect(() => {
    if (incoming) setSource(incoming.path)
  }, [incoming])

  return (
    <Workbench
      controls={
        <>
          <ImageSource label="Image" value={source} onChange={setSource} last={lastGenerated} />
          <p className="text-xs leading-relaxed text-muted">
            Works best with characters and objects on a plain background, which is how they come out of Create.
          </p>
          <RunBar
            label="Remove background"
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
          exclude="remove_bg"
          emptyTitle="Your transparent PNG will appear here"
          emptyHint="Saved to generated_transparent, ready to use as an asset or to send to 3D Model."
        />
      }
    />
  )
}
