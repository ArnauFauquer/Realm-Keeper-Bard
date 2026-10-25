import { Cube } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import { api, thumbUrl, type LibraryFolder, type ResultItem } from '../api'
import { itemKey } from './Stage'
import { Button, cx, Segmented } from './ui'

export const FOLDER_LABELS: Record<LibraryFolder, string> = {
  images: 'Generadas',
  transparent: 'Sin fondo',
  references: 'Referencias',
  models: 'Modelos 3D',
}

const PAGE = 60

/** Rejilla paginada de una carpeta de la app, de más reciente a más antigua. */
export function LibraryGrid({
  folders,
  onPick,
  selectedKey,
  refreshKey = 0,
  dense = false,
}: {
  folders: LibraryFolder[]
  onPick: (item: ResultItem) => void
  selectedKey?: string
  refreshKey?: number
  dense?: boolean
}) {
  const [folder, setFolder] = useState<LibraryFolder>(folders[0])
  const [items, setItems] = useState<ResultItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError('')
    api
      .library(folder, 0, PAGE)
      .then((r) => {
        if (!alive) return
        setItems(r.items)
        setTotal(r.total)
      })
      .catch((e) => alive && setError((e as Error).message))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [folder, refreshKey])

  const loadMore = async () => {
    setLoading(true)
    try {
      const r = await api.library(folder, items.length, PAGE)
      setItems((prev) => [...prev, ...r.items])
      setTotal(r.total)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="grid gap-4">
      {folders.length > 1 && (
        <div className="max-w-xl">
          <Segmented
            label="Carpeta"
            value={folder}
            onChange={setFolder}
            options={folders.map((f) => ({ value: f, label: FOLDER_LABELS[f] }))}
          />
        </div>
      )}

      {error && <p className="text-sm text-danger">{error}</p>}

      <ul
        className={cx(
          'grid gap-2',
          dense
            ? 'grid-cols-3 sm:grid-cols-4 md:grid-cols-5'
            : 'grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6',
        )}
      >
        {items.map((item) => {
          const thumb = item.kind === 'image' ? item.path : item.previews[0]
          const key = itemKey(item)
          return (
            <li key={key}>
              <button
                type="button"
                onClick={() => onPick(item)}
                title={item.name}
                className={cx(
                  'checker group relative block aspect-square w-full overflow-hidden rounded-[10px] border-2 transition-colors',
                  selectedKey === key ? 'border-accent' : 'border-transparent hover:border-line',
                )}
              >
                {thumb ? (
                  <img
                    src={thumbUrl(thumb, 320)}
                    alt={item.name}
                    loading="lazy"
                    className="h-full w-full object-contain transition-transform duration-300 group-hover:scale-[1.03]"
                  />
                ) : (
                  <Cube size={28} className="m-auto text-muted" />
                )}
              </button>
            </li>
          )
        })}
        {loading &&
          Array.from({ length: items.length ? 6 : 12 }, (_, i) => (
            <li key={`sk${i}`} className="shimmer relative aspect-square overflow-hidden rounded-[10px] bg-surface-2" />
          ))}
      </ul>

      {!loading && !items.length && !error && (
        <p className="py-10 text-center text-sm text-muted">Esta carpeta está vacía. Lo que generes aparecerá aquí.</p>
      )}

      {!loading && items.length < total && (
        <div className="flex items-center justify-center gap-3">
          <Button onClick={loadMore}>Cargar más</Button>
          <span className="font-mono text-xs text-muted">
            {items.length} de {total}
          </span>
        </div>
      )}
    </div>
  )
}
