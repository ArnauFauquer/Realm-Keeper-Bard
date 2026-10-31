import { useState } from 'react'
import { useApp } from '../appContext'
import { Select } from '../components/ui'

const NO_SPECIES = ''

/** Style and anatomy templates chosen on a page. Until the dropdown is
 *  touched it follows the default template from Settings; if the chosen one is
 *  deleted, it falls back to the default. */
export function usePresetChoice() {
  const { library } = useApp()
  const [style, setStyle] = useState<string | null>(null)
  const [species, setSpecies] = useState<string | null>(null)

  const styles = library?.styles ?? []
  const speciesList = library?.species ?? []
  const styleId = styles.some((s) => s.id === style) ? style! : (library?.active_style ?? '')
  const speciesId =
    species === NO_SPECIES || speciesList.some((s) => s.id === species)
      ? species!
      : speciesList.some((s) => s.id === library?.active_species)
        ? library!.active_species
        : NO_SPECIES

  return { styleId, setStyle, speciesId, setSpecies }
}

export function PresetSelects({
  isMap,
  withSpecies,
  choice,
}: {
  isMap: boolean
  withSpecies: boolean
  choice: ReturnType<typeof usePresetChoice>
}) {
  const { library } = useApp()
  if (!library) return null
  return (
    <div className="grid gap-4">
      {isMap ? (
        <p className="text-xs leading-relaxed text-muted">
          Maps use the shared map style from Settings, not a style template.
        </p>
      ) : (
        <Select
          label="Style"
          value={choice.styleId}
          onChange={choice.setStyle}
          options={library.styles.map((s) => ({
            value: s.id,
            label: s.id === library.active_style ? `${s.name} (default)` : s.name,
          }))}
        />
      )}
      {withSpecies && (
        <Select
          label="Anatomy"
          value={choice.speciesId}
          onChange={choice.setSpecies}
          options={[
            ...library.species.map((s) => ({
              value: s.id,
              label: s.id === library.active_species ? `${s.name} (default)` : s.name,
            })),
            { value: NO_SPECIES, label: 'No anatomy' },
          ]}
        />
      )}
    </div>
  )
}
