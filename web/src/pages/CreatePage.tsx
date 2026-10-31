import { PaintBrush } from '@phosphor-icons/react'
import { useState } from 'react'
import { api, type Category } from '../api'
import { useApp } from '../appContext'
import { Stage } from '../components/Stage'
import { TextArea, Toggle } from '../components/ui'
import { useElapsed, useJob } from '../useJob'
import { CategoryPicker } from './categories'
import { PresetSelects, usePresetChoice } from './presetChoice'
import { RunBar, useResults, Workbench } from './Workbench'

const PLACEHOLDERS: Record<Category, string> = {
  character: 'A chubby, cheerful blacksmith rat with a leather apron and a hammer on their shoulder...',
  background: 'The market square of a rat village at sunset, wide view...',
  object: 'A brass lantern with a firefly trapped inside...',
  map: 'The region of "Acorn Valley": the village of "Deep Root" by the river and the "Whispering Forest" to the north...',
}

export function CreatePage() {
  const { noteResult } = useApp()
  const results = useResults()
  const [category, setCategory] = useState<Category>('character')
  const [description, setDescription] = useState('')
  const preset = usePresetChoice()
  const [removeBg, setRemoveBg] = useState(false)
  const job = useJob((item) => {
    results.add(item)
    if (item.kind === 'image') noteResult(item.path, item.path.startsWith('generated_transparent'))
  })
  const elapsed = useElapsed(!!job.active, job.since)

  const run = () =>
    job.start(() => api.create({ category, description, style_id: preset.styleId, species_id: preset.speciesId, remove_bg: removeBg }))

  return (
    <Workbench
      controls={
        <>
          <CategoryPicker value={category} onChange={setCategory} />
          <PresetSelects isMap={category === 'map'} withSpecies={category === 'character'} choice={preset} />
          <TextArea
            label="Description"
            minRows={6}
            value={description}
            placeholder={PLACEHOLDERS[category]}
            onChange={(e) => setDescription(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && description.trim()) run()
            }}
            hint={
              category === 'map'
                ? 'Put place names in quotes so they are written exactly as given. Ctrl+Enter to generate.'
                : 'Ctrl+Enter to generate.'
            }
          />
          <div className="grid gap-2">
            <Toggle checked={removeBg} onChange={setRemoveBg} label="Remove the background when done" />
          </div>
          <RunBar
            label="Generate image"
            icon={<PaintBrush size={18} />}
            running={job.running}
            queued={job.queued + (job.active ? 1 : 0)}
            disabled={!description.trim()}
            onRun={run}
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
          category={category}
          emptyTitle="Your image will appear here"
          emptyHint="Describe what you want on the left. It is drawn in your world style defined in Settings."
        />
      }
    />
  )
}
