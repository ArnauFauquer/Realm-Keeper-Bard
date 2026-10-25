import { ArrowsClockwise, ArrowSquareOut, FolderOpen } from '@phosphor-icons/react'
import { useState } from 'react'
import { api, type ResultItem } from '../api'
import { ImageViewer } from '../components/ImageViewer'
import { LibraryGrid } from '../components/LibraryGrid'
import { MeshViewer } from '../components/MeshViewer'
import { Modal } from '../components/Modal'
import { SendActions } from '../components/Stage'
import { fileUrl } from '../api'
import { Button, Panel } from '../components/ui'

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
            </div>
          </div>
        )}
      </Modal>
    </Panel>
  )
}
