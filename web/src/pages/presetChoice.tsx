import { useState } from 'react'
import { useApp } from '../appContext'
import { Select } from '../components/ui'

const NO_SPECIES = ''

/** Plantilla de estilo y de anatomía elegidas en una página. Mientras no se
 *  toca el desplegable sigue la plantilla por defecto de Ajustes; si la elegida
 *  se borra, vuelve a la de por defecto. */
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
          Los mapas usan el estilo de mapa común de Ajustes, no una plantilla de estilo.
        </p>
      ) : (
        <Select
          label="Estilo"
          value={choice.styleId}
          onChange={choice.setStyle}
          options={library.styles.map((s) => ({
            value: s.id,
            label: s.id === library.active_style ? `${s.name} (por defecto)` : s.name,
          }))}
        />
      )}
      {withSpecies && (
        <Select
          label="Anatomía"
          value={choice.speciesId}
          onChange={choice.setSpecies}
          options={[
            ...library.species.map((s) => ({
              value: s.id,
              label: s.id === library.active_species ? `${s.name} (por defecto)` : s.name,
            })),
            { value: NO_SPECIES, label: 'Sin anatomía' },
          ]}
        />
      )}
    </div>
  )
}
