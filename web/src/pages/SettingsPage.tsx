import { CheckCircle, Copy, Cube, FloppyDisk, Images, Plus, Star, Trash, UploadSimple, X } from '@phosphor-icons/react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { api, thumbUrl, type Category, type SpeciesPreset, type StyleData, type StylePreset } from '../api'
import { useApp } from '../appContext'
import { LibraryGrid } from '../components/LibraryGrid'
import { Modal } from '../components/Modal'
import { Button, cx, Panel, Segmented, TextArea, TextInput } from '../components/ui'
import { CATEGORY_OPTIONS } from './categories'

function Section({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <Panel className="grid gap-5 p-5 md:grid-cols-[minmax(0,15rem)_minmax(0,1fr)] md:gap-8 md:p-6">
      <div className="grid content-start gap-1.5">
        <h2 className="text-base font-semibold text-fg">{title}</h2>
        <p className="text-xs leading-relaxed text-muted">{description}</p>
      </div>
      <div className="grid min-w-0 gap-4">{children}</div>
    </Panel>
  )
}

// Tabs for the shared settings: the four image types + the 3D model.
type Kind = Category | 'model_3d'
const KIND_OPTIONS: { value: Kind; label: string; icon: ReactNode }[] = [
  ...CATEGORY_OPTIONS,
  { value: 'model_3d', label: '3D Model', icon: <Cube size={18} /> },
]

const newId = () => `p${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`

/** Template row: one pill per template (the star marks the default) and
 *  another to create a new one. */
function PresetTabs({
  items,
  selected,
  active,
  onSelect,
  onAdd,
  addLabel,
}: {
  items: { id: string; name: string }[]
  selected: string
  active: string
  onSelect: (id: string) => void
  onAdd: () => void
  addLabel: string
}) {
  return (
    <div className="flex flex-wrap gap-2" role="tablist">
      {items.map((p) => (
        <button
          key={p.id}
          type="button"
          role="tab"
          aria-selected={selected === p.id}
          onClick={() => onSelect(p.id)}
          className={cx(
            'inline-flex h-9 max-w-full items-center gap-1.5 rounded-full border px-3.5 text-sm transition-colors',
            'focus-visible:outline-2 focus-visible:outline-accent',
            selected === p.id
              ? 'border-accent bg-accent-soft text-accent'
              : 'border-line text-muted hover:border-muted/60 hover:text-fg',
          )}
        >
          {p.id === active && <Star size={13} weight="fill" aria-label="Default" />}
          <span className="truncate">{p.name || 'Unnamed'}</span>
        </button>
      ))}
      <button
        type="button"
        onClick={onAdd}
        className="inline-flex h-9 items-center gap-1.5 rounded-full border border-dashed border-line px-3.5 text-sm text-muted transition-colors hover:border-muted/60 hover:text-fg focus-visible:outline-2 focus-visible:outline-accent"
      >
        <Plus size={14} /> {addLabel}
      </button>
    </div>
  )
}

function PresetActions({
  name,
  isActive,
  canDelete,
  onDuplicate,
  onMakeActive,
  onDelete,
}: {
  name: string
  isActive: boolean
  canDelete: boolean
  onDuplicate: () => void
  onMakeActive: () => void
  onDelete: () => void
}) {
  const [confirming, setConfirming] = useState(false)
  useEffect(() => setConfirming(false), [name])
  if (confirming) {
    return (
      <div className="flex flex-wrap items-center gap-2 rounded-[10px] border border-danger/35 bg-danger/8 px-3 py-2">
        <span className="text-sm text-fg">Delete “{name || 'Unnamed'}”?</span>
        <Button variant="danger" className="h-9" onClick={onDelete}>
          <Trash size={16} /> Delete
        </Button>
        <Button variant="ghost" className="h-9" onClick={() => setConfirming(false)}>
          Cancel
        </Button>
      </div>
    )
  }
  return (
    <div className="flex flex-wrap gap-2">
      <Button variant="ghost" className="h-9" onClick={onMakeActive} disabled={isActive}>
        <Star size={16} weight={isActive ? 'fill' : 'regular'} /> {isActive ? 'Default' : 'Use as default'}
      </Button>
      <Button variant="ghost" className="h-9" onClick={onDuplicate}>
        <Copy size={16} /> Duplicar
      </Button>
      <Button
        variant="ghost"
        className="h-9 hover:text-danger"
        onClick={() => setConfirming(true)}
        disabled={!canDelete}
        title={canDelete ? undefined : 'At least one style must remain'}
      >
        <Trash size={16} /> Delete
      </Button>
    </div>
  )
}

function AnchorImage({ value, onChange }: { value: string | null; onChange: (path: string) => void }) {
  const [picking, setPicking] = useState(false)
  const [error, setError] = useState('')
  const input = useRef<HTMLInputElement>(null)
  return (
    <div className="grid gap-2">
      <span className="text-sm font-medium text-fg">Anchor image</span>
      <div className="flex items-start gap-4">
        <div className="checker grid h-36 w-28 shrink-0 place-items-center overflow-hidden rounded-[10px] border border-line">
          {value ? (
            <img src={thumbUrl(value, 320)} alt="Anatomy anchor image" className="h-full w-full object-contain" />
          ) : (
            <span className="px-2 text-center text-xs text-muted">No image</span>
          )}
        </div>
        <div className="grid gap-2">
          <p className="max-w-[40ch] text-xs leading-relaxed text-muted">
            When transforming characters it is attached as the base body: the model sees the anatomy instead of only reading it.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => setPicking(true)}>
              <Images size={16} /> Choose
            </Button>
            <Button onClick={() => input.current?.click()}>
              <UploadSimple size={16} /> Upload
            </Button>
            {value && (
              <Button variant="ghost" onClick={() => onChange('')}>
                <X size={16} /> Remove
              </Button>
            )}
          </div>
          {error && <p className="text-xs text-danger">{error}</p>}
        </div>
      </div>
      <input
        ref={input}
        type="file"
        accept="image/*"
        hidden
        onChange={async (e) => {
          const file = e.target.files?.[0]
          e.target.value = ''
          if (!file) return
          try {
            onChange((await api.upload(file)).path)
          } catch (err) {
            setError((err as Error).message)
          }
        }}
      />
      <Modal open={picking} onClose={() => setPicking(false)} title="Anchor image" wide>
        <LibraryGrid
          folders={['references', 'images', 'transparent']}
          dense
          selectedKey={value ?? undefined}
          onPick={(item) => {
            if (item.kind === 'image') onChange(item.path)
            setPicking(false)
          }}
        />
      </Modal>
    </div>
  )
}

// species_ref_resolved is computed by the server: it does not count as a change
const comparable = (d: StyleData) =>
  JSON.stringify({ ...d, species: d.species.map(({ species_ref_resolved: _, ...s }) => s) })

export function SettingsPage() {
  const { setLibrary } = useApp()
  const [saved, setSaved] = useState<StyleData | null>(null)
  const [draft, setDraft] = useState<StyleData | null>(null)
  const [styleSel, setStyleSel] = useState('')
  const [speciesSel, setSpeciesSel] = useState('')
  const [kind, setKind] = useState<Kind>('character')
  const [status, setStatus] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    api
      .style()
      .then((s) => {
        setSaved(s)
        setDraft(s)
        setStyleSel(s.active_style)
        setSpeciesSel(s.active_species || s.species[0]?.id || '')
      })
      .catch((e) => setLoadError((e as Error).message))
  }, [])

  if (loadError) return <p className="text-sm text-danger">No se pudo cargar el estilo: {loadError}</p>
  if (!draft || !saved) {
    return (
      <div className="grid gap-4">
        {[0, 1, 2].map((i) => (
          <div key={i} className="shimmer relative h-48 overflow-hidden rounded-2xl bg-surface-2" />
        ))}
      </div>
    )
  }

  const update = (next: Partial<StyleData>) => {
    setDraft({ ...draft, ...next })
    setStatus(null)
  }
  const dirty = comparable(draft) !== comparable(saved)

  const style = draft.styles.find((s) => s.id === styleSel) ?? draft.styles[0]
  const setStyleField = (patch: Partial<StylePreset>) =>
    update({ styles: draft.styles.map((s) => (s.id === style.id ? { ...s, ...patch } : s)) })
  const addStyle = (base?: StylePreset) => {
    const preset: StylePreset = base
      ? { ...base, id: newId(), name: `${base.name} (copia)` }
      : { id: newId(), name: 'New style', style_prompt: '', constraints: draft.styles[0]?.constraints ?? '' }
    update({ styles: [...draft.styles, preset] })
    setStyleSel(preset.id)
  }
  const deleteStyle = () => {
    const rest = draft.styles.filter((s) => s.id !== style.id)
    update({ styles: rest, active_style: draft.active_style === style.id ? rest[0].id : draft.active_style })
    setStyleSel(rest[0].id)
  }

  const species = draft.species.find((s) => s.id === speciesSel) ?? draft.species[0]
  const setSpeciesField = (patch: Partial<SpeciesPreset>) =>
    update({ species: draft.species.map((s) => (s.id === species.id ? { ...s, ...patch } : s)) })
  const addSpecies = (base?: SpeciesPreset) => {
    const preset: SpeciesPreset = base
      ? { ...base, id: newId(), name: `${base.name} (copia)` }
      : { id: newId(), name: 'New anatomy', species_prompt: '', species_ref: '' }
    update({ species: [...draft.species, preset], active_species: draft.active_species || preset.id })
    setSpeciesSel(preset.id)
  }
  const deleteSpecies = () => {
    const rest = draft.species.filter((s) => s.id !== species.id)
    update({
      species: rest,
      active_species: draft.active_species === species.id ? (rest[0]?.id ?? '') : draft.active_species,
    })
    setSpeciesSel(rest[0]?.id ?? '')
  }
  // the saved path may not exist: preview the one resolved by the server
  const savedSpecies = species && saved.species.find((s) => s.id === species.id)
  const anchorPreview = !species
    ? null
    : savedSpecies && savedSpecies.species_ref === species.species_ref
      ? (savedSpecies.species_ref_resolved ?? null)
      : species.species_ref || null

  const save = async () => {
    const blank = [...draft.styles, ...draft.species].find((p) => !p.name.trim())
    if (blank) {
      setStatus({ kind: 'error', text: 'All templates need a name.' })
      return
    }
    setSaving(true)
    try {
      const s = await api.saveStyle(draft)
      setSaved(s)
      setDraft(s)
      setLibrary(s)
      setStatus({ kind: 'ok', text: 'Saved. Applies from the next generation.' })
    } catch (e) {
      setStatus({ kind: 'error', text: (e as Error).message })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="grid gap-5 pb-24">
      <Section
        title="Styles"
        description="General style templates. When creating or transforming you choose which one to use; the star marks the default. They are not used for maps."
      >
        <PresetTabs
          items={draft.styles}
          selected={style.id}
          active={draft.active_style}
          onSelect={setStyleSel}
          onAdd={() => addStyle()}
          addLabel="New style"
        />
        <div key={style.id} className="grid gap-4">
          <TextInput label="Name" value={style.name} onChange={(v) => setStyleField({ name: v })} />
          <TextArea
            label="Style prompt"
            minRows={8}
            value={style.style_prompt}
            placeholder="Describe the visual style that will be repeated identically in every image."
            onChange={(e) => setStyleField({ style_prompt: e.target.value })}
          />
          <TextArea
            label="Constraints"
            minRows={2}
            value={style.constraints}
            onChange={(e) => setStyleField({ constraints: e.target.value })}
          />
          <PresetActions
            name={style.name}
            isActive={draft.active_style === style.id}
            canDelete={draft.styles.length > 1}
            onMakeActive={() => update({ active_style: style.id })}
            onDuplicate={() => addStyle(style)}
            onDelete={deleteStyle}
          />
        </div>
      </Section>

      <Section
        title="Anatomies"
        description="Species anatomy templates, for characters only. They separate what belongs to the species from what belongs to each individual."
      >
        <PresetTabs
          items={draft.species}
          selected={species?.id ?? ''}
          active={draft.active_species}
          onSelect={setSpeciesSel}
          onAdd={() => addSpecies()}
          addLabel="New anatomy"
        />
        {species ? (
          <div key={species.id} className="grid gap-4">
            <TextInput label="Name" value={species.name} onChange={(v) => setSpeciesField({ name: v })} />
            <TextArea
              label="Anatomy description"
              minRows={7}
              value={species.species_prompt}
              placeholder="Head, body, hands, feet, tail... and which traits belong to each individual."
              onChange={(e) => setSpeciesField({ species_prompt: e.target.value })}
            />
            <AnchorImage value={anchorPreview} onChange={(p) => setSpeciesField({ species_ref: p })} />
            <PresetActions
              name={species.name}
              isActive={draft.active_species === species.id}
              canDelete
              onMakeActive={() => update({ active_species: species.id })}
              onDuplicate={() => addSpecies(species)}
              onDelete={deleteSpecies}
            />
          </div>
        ) : (
          <p className="text-sm text-muted">No anatomies. Characters will be generated without species anatomy.</p>
        )}
      </Section>

      <Section
        title="Point of view"
        description="Settings shared by all templates, per type. Maps and 3D models also have their own style here."
      >
        <Segmented label="Type" value={kind} onChange={setKind} options={KIND_OPTIONS} stacked />
        <div key={kind} className="grid gap-4">
          {kind === 'model_3d' ? (
            <TextArea
              label="Sculpture style"
              hint="Only when preparing the image with FLUX 3 in detailed sculpture mode."
              minRows={6}
              value={draft.style_3d}
              onChange={(e) => update({ style_3d: e.target.value })}
            />
          ) : (
            <TextArea
              label="Framing and camera"
              minRows={7}
              value={draft.pov[kind] ?? ''}
              onChange={(e) => update({ pov: { ...draft.pov, [kind]: e.target.value } })}
            />
          )}
          {kind === 'map' && (
            <>
              <TextArea
                label="Map style"
                hint="Replaces the template style, because a map is drawn like a cartographer's map."
                minRows={6}
                value={draft.map_style}
                onChange={(e) => update({ map_style: e.target.value })}
              />
              <TextArea
                label="Map constraints"
                hint="Replace the template's, because a map needs labels."
                minRows={4}
                value={draft.map_constraints}
                onChange={(e) => update({ map_constraints: e.target.value })}
              />
            </>
          )}
        </div>
      </Section>

      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/95 backdrop-blur lg:left-[248px]">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-3 px-4 py-3 md:px-8">
          <Button variant="primary" onClick={save} disabled={!dirty || saving}>
            <FloppyDisk size={16} /> {saving ? 'Saving...' : 'Save'}
          </Button>
          {dirty && (
            <Button
              variant="ghost"
              onClick={() => {
                setDraft(saved)
                setStatus(null)
              }}
            >
              Discard changes
            </Button>
          )}
          <p className="text-xs text-muted" role="status">
            {status ? (
              <span className={status.kind === 'ok' ? 'inline-flex items-center gap-1.5 text-ok' : 'text-danger'}>
                {status.kind === 'ok' && <CheckCircle size={14} />}
                {status.text}
              </span>
            ) : dirty ? (
              'There are unsaved changes.'
            ) : (
              'All saved.'
            )}
          </p>
        </div>
      </div>
    </div>
  )
}
