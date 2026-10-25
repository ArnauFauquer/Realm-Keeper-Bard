import { MapTrifold, Mountains, Person, Sword } from '@phosphor-icons/react'
import type { Category } from '../api'
import { Segmented } from '../components/ui'

export const CATEGORY_OPTIONS: { value: Category; label: string; icon: React.ReactNode }[] = [
  { value: 'personaje', label: 'Personaje', icon: <Person size={18} /> },
  { value: 'fondo', label: 'Fondo', icon: <Mountains size={18} /> },
  { value: 'objeto', label: 'Objeto', icon: <Sword size={18} /> },
  { value: 'mapa', label: 'Mapa', icon: <MapTrifold size={18} /> },
]

export function CategoryPicker({ value, onChange }: { value: Category; onChange: (c: Category) => void }) {
  return <Segmented label="Tipo" value={value} onChange={onChange} options={CATEGORY_OPTIONS} stacked />
}
