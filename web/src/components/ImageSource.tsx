import { ClockCounterClockwise, Images, UploadSimple, X } from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'
import { api, thumbUrl, type LibraryFolder } from '../api'
import { LibraryGrid } from './LibraryGrid'
import { Modal } from './Modal'
import { Button, cx, IconButton } from './ui'

/** Imagen de entrada: arrastrar y soltar, pegar, subir, elegir de la
 *  biblioteca o reutilizar la última de la sesión. */
export function ImageSource({
  label,
  value,
  onChange,
  last,
  folders = ['images', 'transparent', 'references'],
}: {
  label: string
  value: string | null
  onChange: (path: string | null) => void
  last?: string | null
  folders?: LibraryFolder[]
}) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [picking, setPicking] = useState(false)
  const zone = useRef<HTMLDivElement>(null)

  // Ctrl+V en cualquier parte de la página visible (salvo si se escribe en un campo).
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const file = e.clipboardData?.files[0]
      const typing = document.activeElement?.matches('textarea, input')
      if (!file || typing || !zone.current?.offsetParent) return
      e.preventDefault()
      upload(file)
    }
    window.addEventListener('paste', onPaste)
    return () => window.removeEventListener('paste', onPaste)
  })

  const upload = async (file: File | undefined) => {
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setError('Eso no es una imagen.')
      return
    }
    setBusy(true)
    setError('')
    try {
      onChange((await api.upload(file)).path)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid gap-2">
      <span className="text-sm font-medium text-fg">{label}</span>
      <div
        ref={zone}
        tabIndex={0}
        role="button"
        aria-label={`${label}: arrastra, pega o pulsa para subir una imagen`}
        onClick={() => !value && input.current?.click()}
        onKeyDown={(e) => {
          if ((e.key === 'Enter' || e.key === ' ') && !value) input.current?.click()
        }}
        onDragOver={(e) => {
          e.preventDefault()
          setOver(true)
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setOver(false)
          upload(e.dataTransfer.files[0])
        }}
        className={cx(
          'relative grid h-44 place-items-center overflow-hidden rounded-[10px] border border-dashed transition-colors',
          'focus-visible:outline-2 focus-visible:outline-accent',
          over ? 'border-accent bg-accent-soft' : 'border-line bg-bg',
          !value && 'cursor-pointer hover:border-muted/60',
          busy && 'shimmer',
        )}
      >
        {value ? (
          <>
            <img src={thumbUrl(value, 480)} alt="" className="checker h-full w-full object-contain" />
            <IconButton
              label="Quitar imagen"
              onClick={(e) => {
                e.stopPropagation()
                onChange(null)
              }}
              className="absolute right-2 top-2 size-8 rounded-full border border-line bg-surface/90 backdrop-blur"
            >
              <X size={14} />
            </IconButton>
          </>
        ) : (
          <div className="grid justify-items-center gap-2 px-6 text-center">
            <UploadSimple size={22} className="text-muted" />
            <p className="text-sm text-fg">Arrastra una imagen o pulsa para subirla</p>
            <p className="text-xs text-muted">También puedes pegarla con Ctrl+V</p>
          </div>
        )}
      </div>
      <input
        ref={input}
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => {
          upload(e.target.files?.[0])
          e.target.value = ''
        }}
      />
      <div className="grid grid-cols-2 gap-2">
        <Button onClick={() => setPicking(true)}>
          <Images size={16} /> Biblioteca
        </Button>
        <Button disabled={!last} onClick={() => last && onChange(last)} title={last ? undefined : 'Aún no has generado nada en esta sesión'}>
          <ClockCounterClockwise size={16} /> Usar la última
        </Button>
      </div>
      {error && <p className="text-xs text-danger">{error}</p>}

      <Modal open={picking} onClose={() => setPicking(false)} title="Elegir de la biblioteca" wide>
        <LibraryGrid
          folders={folders}
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
