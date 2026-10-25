import {
  CircleHalf,
  Cube,
  Images,
  Lightning,
  MagicWand,
  Moon,
  PaintBrush,
  Scissors,
  SlidersHorizontal,
  Sun,
} from '@phosphor-icons/react'
import { MotionConfig } from 'motion/react'
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, jobActive, type EngineInfo, type Job, type Options, type StyleData } from './api'
import { AppContext, JOB_PAGE, type AppState, type PageKey, type SendTarget } from './appContext'
import { QueuePanel } from './components/QueuePanel'
import { Button, cx, PageHeader } from './components/ui'
import { CreatePage } from './pages/CreatePage'
import { LibraryPage } from './pages/LibraryPage'
import { MeshPage } from './pages/MeshPage'
import { RemoveBgPage } from './pages/RemoveBgPage'
import { SettingsPage } from './pages/SettingsPage'
import { TransformPage } from './pages/TransformPage'

const PAGES: { key: PageKey; label: string; title: string; subtitle: string; icon: ReactNode }[] = [
  {
    key: 'crear',
    label: 'Crear',
    title: 'Crear',
    subtitle: 'Un personaje, un fondo, un objeto o un mapa nuevo, con el estilo de tu mundo.',
    icon: <PaintBrush size={18} />,
  },
  {
    key: 'transformar',
    label: 'Transformar',
    title: 'Transformar al estilo',
    subtitle: 'Redibuja una imagen de referencia con tu estilo, conservando su identidad.',
    icon: <MagicWand size={18} />,
  },
  {
    key: 'quitar_fondo',
    label: 'Quitar fondo',
    title: 'Quitar fondo',
    subtitle: 'Convierte una imagen en un PNG transparente, listo para usar como asset.',
    icon: <Scissors size={18} />,
  },
  {
    key: 'modelo_3d',
    label: 'Modelo 3D',
    title: 'Modelo 3D',
    subtitle: 'Convierte una imagen en una miniatura imprimible (STL).',
    icon: <Cube size={18} />,
  },
  {
    key: 'biblioteca',
    label: 'Biblioteca',
    title: 'Biblioteca',
    subtitle: 'Todo lo que has generado, de lo más reciente a lo más antiguo.',
    icon: <Images size={18} />,
  },
  {
    key: 'ajustes',
    label: 'Ajustes de estilo',
    title: 'Ajustes de estilo',
    subtitle: 'Tus plantillas de estilo y de anatomía, y los ajustes comunes a todas.',
    icon: <SlidersHorizontal size={18} />,
  },
]

const pageFromHash = (): PageKey => {
  const key = window.location.hash.replace('#/', '') as PageKey
  return PAGES.some((p) => p.key === key) ? key : 'crear'
}

type Theme = 'auto' | 'light' | 'dark'

function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      return (localStorage.getItem('rkb-theme') as Theme) || 'auto'
    } catch {
      return 'auto'
    }
  })
  useEffect(() => {
    const root = document.documentElement
    if (theme === 'auto') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', theme)
    try {
      localStorage.setItem('rkb-theme', theme)
    } catch {
      /* almacenamiento bloqueado: solo se pierde la preferencia */
    }
  }, [theme])
  const next = () => setTheme((t) => (t === 'auto' ? 'dark' : t === 'dark' ? 'light' : 'auto'))
  return { theme, next }
}

const ENGINE_TONE: Record<EngineInfo['status'], string> = {
  ready: 'bg-ok',
  starting: 'bg-accent animate-pulse motion-reduce:animate-none',
  stopped: 'bg-muted',
  error: 'bg-danger',
}

function EngineCard() {
  const [engine, setEngine] = useState<EngineInfo>({ status: 'starting', message: 'Conectando...' })
  const [offline, setOffline] = useState(false)

  useEffect(() => {
    let alive = true
    let timer: number
    const tick = async () => {
      try {
        const e = await api.engine()
        if (!alive) return
        setEngine(e)
        setOffline(false)
      } catch {
        if (alive) setOffline(true)
      }
      timer = window.setTimeout(tick, 3000)
    }
    tick()
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
  }, [])

  const info = offline ? { status: 'error' as const, message: 'Sin conexión con el servidor de la app.' } : engine

  return (
    <div className="grid gap-3 rounded-2xl border border-line bg-bg p-3.5">
      <div className="flex items-center gap-2">
        <Lightning size={16} className="text-muted" />
        <span className="text-sm font-medium text-fg">Motor local</span>
        <span
          className={cx('ml-auto size-2 rounded-full', ENGINE_TONE[info.status])}
          aria-label={`Estado: ${info.status}`}
        />
      </div>
      <p className="text-xs leading-relaxed text-muted">{info.message}</p>
      <p className="text-[11px] leading-relaxed text-muted/80">Crear con Krea 2. Editar con FLUX 3.</p>
      {(info.status === 'stopped' || info.status === 'error') && !offline && (
        <Button className="h-9" onClick={async () => setEngine(await api.startEngine())}>
          Arrancar motor
        </Button>
      )}
    </div>
  )
}

/** Cola del servidor: se consulta cada segundo mientras hay algo pendiente y,
 *  si no, de vez en cuando (por si se encoló desde otra pestaña). */
function useJobs() {
  const [jobs, setJobs] = useState<Job[]>([])
  const busy = useRef(false)
  useEffect(() => {
    busy.current = jobs.some(jobActive)
  }, [jobs])

  useEffect(() => {
    let alive = true
    let timer: number
    const tick = async () => {
      try {
        const list = await api.jobs()
        if (alive) setJobs(list)
      } catch {
        /* servidor caído: EngineCard ya lo avisa */
      }
      if (alive) timer = window.setTimeout(tick, busy.current ? 900 : 4000)
    }
    tick()
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
  }, [])

  const trackJob = useCallback((job: Job) => {
    busy.current = busy.current || jobActive(job)
    setJobs((prev) => (prev.some((j) => j.id === job.id) ? prev.map((j) => (j.id === job.id ? job : j)) : [...prev, job]))
  }, [])

  return { jobs, trackJob }
}

export default function App() {
  const [page, setPage] = useState<PageKey>(pageFromHash)
  const [options, setOptions] = useState<Options | null>(null)
  const [inbox, setInbox] = useState<AppState['inbox']>({})
  const [lastGenerated, setLastGenerated] = useState<string | null>(null)
  const [lastTransparent, setLastTransparent] = useState<string | null>(null)
  const [libraryVersion, setLibraryVersion] = useState(0)
  const [library, setLibrary] = useState<StyleData | null>(null)
  const { theme, next: nextTheme } = useTheme()
  const { jobs, trackJob } = useJobs()

  useEffect(() => {
    const onHash = () => setPage(pageFromHash())
    window.addEventListener('hashchange', onHash)
    api.options().then(setOptions).catch(() => setOptions(null))
    api.style().then(setLibrary).catch(() => setLibrary(null))
    api
      .last()
      .then((l) => {
        setLastGenerated((v) => v ?? l.generated)
        setLastTransparent((v) => v ?? l.transparent)
      })
      .catch(() => {})
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const go = useCallback((key: PageKey) => {
    window.location.hash = `/${key}`
    setPage(key)
  }, [])

  const sendTo = useCallback(
    (target: SendTarget, path: string) => {
      setInbox((prev) => ({ ...prev, [target]: { path, n: (prev[target]?.n ?? 0) + 1 } }))
      go(target)
    },
    [go],
  )

  const noteResult = useCallback((path: string, transparent: boolean) => {
    if (transparent) setLastTransparent(path)
    else setLastGenerated(path)
    setLibraryVersion((n) => n + 1)
  }, [])

  const ctx = useMemo<AppState>(
    () => ({ options, go, jobs, trackJob, sendTo, inbox, lastGenerated, lastTransparent, noteResult, library, setLibrary }),
    [options, go, jobs, trackJob, sendTo, inbox, lastGenerated, lastTransparent, noteResult, library],
  )

  const current = PAGES.find((p) => p.key === page)!
  const pending: Partial<Record<PageKey, number>> = {}
  for (const job of jobs.filter(jobActive)) pending[JOB_PAGE[job.kind]] = (pending[JOB_PAGE[job.kind]] ?? 0) + 1

  return (
    <AppContext.Provider value={ctx}>
      <MotionConfig reducedMotion="user">
        <div className="min-h-[100dvh] lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
          <aside className="border-b border-line bg-surface lg:sticky lg:top-0 lg:flex lg:h-[100dvh] lg:flex-col lg:border-b-0 lg:border-r">
            <div className="flex items-center justify-between px-4 py-4 lg:block lg:px-5 lg:pb-6 lg:pt-6">
              <div>
                <p className="text-[17px] font-semibold tracking-tight text-fg">RealmKeeper Bard</p>
                <p className="text-xs text-muted">Forja de assets de D&amp;D</p>
              </div>
              <button
                type="button"
                onClick={nextTheme}
                className="inline-flex size-9 items-center justify-center rounded-[10px] text-muted hover:bg-surface-2 hover:text-fg lg:hidden"
                aria-label={`Tema: ${theme}`}
              >
                {theme === 'auto' ? <CircleHalf size={18} /> : theme === 'dark' ? <Moon size={18} /> : <Sun size={18} />}
              </button>
            </div>
            <nav aria-label="Secciones" className="scroll-thin overflow-x-auto px-3 pb-3 lg:overflow-visible lg:pb-0">
              <ul className="flex gap-1 lg:grid">
                {PAGES.map((p) => (
                  <li key={p.key} className={p.key === 'biblioteca' ? 'lg:mt-4 lg:border-t lg:border-line lg:pt-4' : undefined}>
                    <button
                      type="button"
                      onClick={() => go(p.key)}
                      aria-current={page === p.key ? 'page' : undefined}
                      className={cx(
                        'flex h-10 w-full items-center gap-3 whitespace-nowrap rounded-[10px] px-3 text-sm transition-colors duration-200',
                        'focus-visible:outline-2 focus-visible:outline-accent',
                        page === p.key
                          ? 'bg-accent-soft font-medium text-accent'
                          : 'text-muted hover:bg-surface-2 hover:text-fg',
                      )}
                    >
                      {p.icon}
                      {p.label}
                      {pending[p.key] && (
                        <span
                          className="ml-auto rounded-full bg-accent px-1.5 py-px font-mono text-[10px] leading-4 text-on-accent"
                          aria-label={`${pending[p.key]} en la cola`}
                        >
                          {pending[p.key]}
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            </nav>
            <div className="mt-auto hidden gap-3 p-4 lg:grid">
              <QueuePanel />
              <EngineCard />
              <button
                type="button"
                onClick={nextTheme}
                className="flex h-9 items-center gap-2 rounded-[10px] px-3 text-xs text-muted hover:bg-surface-2 hover:text-fg"
              >
                {theme === 'auto' ? <CircleHalf size={16} /> : theme === 'dark' ? <Moon size={16} /> : <Sun size={16} />}
                Tema: {theme === 'auto' ? 'automático' : theme === 'dark' ? 'oscuro' : 'claro'}
              </button>
            </div>
          </aside>

          <main className="mx-auto w-full max-w-[1400px] px-4 py-6 md:px-8 lg:py-8">
            <PageHeader title={current.title} subtitle={current.subtitle} />
            <div className="mb-5 grid gap-3 lg:hidden">
              <QueuePanel />
              <EngineCard />
            </div>
            {/* Las páginas siguen montadas al cambiar de sección (como tkraise en la
                GUI): no se pierden los textos, las imágenes ni los trabajos en marcha. */}
            <div hidden={page !== 'crear'}>
              <CreatePage />
            </div>
            <div hidden={page !== 'transformar'}>
              <TransformPage />
            </div>
            <div hidden={page !== 'quitar_fondo'}>
              <RemoveBgPage />
            </div>
            <div hidden={page !== 'modelo_3d'}>
              <MeshPage />
            </div>
            <div hidden={page !== 'biblioteca'}>
              <LibraryPage refreshKey={libraryVersion} />
            </div>
            <div hidden={page !== 'ajustes'}>
              <SettingsPage />
            </div>
          </main>
        </div>
      </MotionConfig>
    </AppContext.Provider>
  )
}
