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
  personaje: 'Una rata herrera, gorda y risueña, con delantal de cuero y un martillo al hombro...',
  fondo: 'La plaza del mercado de un pueblo de ratas al atardecer, vista amplia...',
  objeto: 'Una linterna de latón con una luciérnaga atrapada dentro...',
  mapa: 'La comarca de "Valle Bellota": el pueblo "Raíz Honda" junto al río y el "Bosque de los Susurros" al norte...',
}

export function CreatePage() {
  const { noteResult } = useApp()
  const results = useResults()
  const [category, setCategory] = useState<Category>('personaje')
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
          <PresetSelects isMap={category === 'mapa'} withSpecies={category === 'personaje'} choice={preset} />
          <TextArea
            label="Descripción"
            minRows={6}
            value={description}
            placeholder={PLACEHOLDERS[category]}
            onChange={(e) => setDescription(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && description.trim()) run()
            }}
            hint={
              category === 'mapa'
                ? 'Pon los nombres de los lugares entre comillas para que salgan escritos tal cual. Ctrl+Enter para generar.'
                : 'Ctrl+Enter para generar.'
            }
          />
          <div className="grid gap-2">
            <Toggle checked={removeBg} onChange={setRemoveBg} label="Quitar el fondo al terminar" />
          </div>
          <RunBar
            label="Generar imagen"
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
          emptyTitle="Aquí aparecerá la imagen"
          emptyHint="Describe lo que quieres a la izquierda. Se dibuja con el estilo de tu mundo definido en Ajustes."
        />
      }
    />
  )
}
