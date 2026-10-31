import { MapTrifold, Mountains, Person, Sword } from '@phosphor-icons/react'
import type { Category } from '../api'
import { Segmented } from '../components/ui'

export const CATEGORY_OPTIONS: { value: Category; label: string; icon: React.ReactNode }[] = [
  { value: 'character', label: 'Character', icon: <Person size={18} /> },
  { value: 'background', label: 'Background', icon: <Mountains size={18} /> },
  { value: 'object', label: 'Object', icon: <Sword size={18} /> },
  { value: 'map', label: 'Map', icon: <MapTrifold size={18} /> },
]

export function CategoryPicker({ value, onChange }: { value: Category; onChange: (c: Category) => void }) {
  return <Segmented label="Type" value={value} onChange={onChange} options={CATEGORY_OPTIONS} stacked />
}
