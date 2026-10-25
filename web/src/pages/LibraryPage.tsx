import { ArrowsClockwise, ArrowSquareOut, FolderOpen, Trash } from '@phosphor-icons/react'
import { useState } from 'react'
import { api, type ResultItem } from '../api'
import { ImageViewer } from '../components/ImageViewer'
import { LibraryGrid } from '../components/LibraryGrid'
import { MeshViewer } from '../components/MeshViewer'
import { Modal } from '../components/Modal'
import { SendActions } from '../components/Stage'
import { fileUrl } from '../api'
import { Button, Panel } from '../components/ui'

/** Borrar pide un segundo clic: el primero solo arma el botón. */
function DeleteButton({ item, onDeleted }: { item: ResultItem; onDeleted: () => void }) {
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const remove = async () => {
    if (!armed) {
      setArmed(true)
      return
    }
    setBusy(true)
    setError('')
    try {
      await api.remove(item.kind === 'image' ? item.path : item.glb)
      onDeleted()
    } catch (e) {
      setError((e as Error).message)
      setArmed(false)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="ml-auto flex items-center gap-2">
      {error && <span className="text-xs text-danger">{error}</span>}
      {armed && !busy && (
        <Button variant="ghost" className="h-9 px-3" onClick={() => setArmed(false)}>
          Cancelar
        </Button>
      )}
      <Button variant="danger" className="h-9 px-3" onClick={remove} disabled={busy}>
        <Trash size={16} /> {armed ? (item.kind === 'image' ? '¿Borrar imagen?' : '¿Borrar modelo 3D?') : 'Borrar'}
      </Button>
    </div>
  )
}

export function LibraryPage({ refreshKey }: { refreshKey: number }) {
  const [open, setOpen] = useState<ResultItem | null>(null)
  const [refresh, setRefresh] = useState(0)

  return (
    <Panel className="p-5">
      <div className="mb-4 flex flex-wrap justify-end gap-2">
        <Button variant="ghost" onClick={() => setRefresh((n) => n + 1)}>
          <ArrowsClockwise size={16} /> Actualizar
        </Button>
      </div>
      <LibraryGrid
        folders={['images', 'transparent', 'models', 'references']}
        refreshKey={refreshKey + refresh}
        onPick={setOpen}
      />
      <Modal open={!!open} onClose={() => setOpen(null)} title={open?.name ?? ''} wide>
        {open && (
          <div className="grid gap-4">
            <div className="h-[62dvh]">
              {open.kind === 'image' ? (
                <ImageViewer src={fileUrl(open.path)} alt={open.name} />
              ) : (
                <div className="checker h-full overflow-hidden rounded-[10px]">
                  <MeshViewer item={open} />
                </div>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-1">
              {open.kind === 'image' ? (
                <>
                  <SendActions path={open.path} onSent={() => setOpen(null)} />
                  <Button variant="ghost" className="h-9 px-3" onClick={() => api.open(open.path)}>
                    <ArrowSquareOut size={16} /> Abrir con Windows
                  </Button>
                </>
              ) : (
                <>
                  {open.stl && (
                    <Button variant="ghost" className="h-9 px-3" onClick={() => api.open(open.stl!)}>
                      <ArrowSquareOut size={16} /> Abrir STL
                    </Button>
                  )}
                  <Button variant="ghost" className="h-9 px-3" onClick={() => api.open(open.glb)}>
                    <ArrowSquareOut size={16} /> Abrir GLB
                  </Button>
                  <Button variant="ghost" className="h-9 px-3" onClick={() => api.open('generated_3d')}>
                    <FolderOpen size={16} /> Carpeta
                  </Button>
                </>
              )}
              <DeleteButton
                key={open.kind === 'image' ? open.path : open.glb}
                item={open}
                onDeleted={() => {
                  setOpen(null)
                  setRefresh((n) => n + 1)
                }}
              />
            </div>
          </div>
        )}
      </Modal>
    </Panel>
  )
}
