import { createContext, useContext } from 'react'
import type { Job, JobKind, Options, StyleData } from './api'

export type PageKey = 'crear' | 'transformar' | 'quitar_fondo' | 'modelo_3d' | 'biblioteca' | 'ajustes'
export type SendTarget = 'transformar' | 'quitar_fondo' | 'modelo_3d'

/** Página desde la que se lanza cada tipo de trabajo. */
export const JOB_PAGE: Record<JobKind, PageKey> = {
  create: 'crear',
  transform: 'transformar',
  remove_bg: 'quitar_fondo',
  mesh: 'modelo_3d',
}

export interface AppState {
  options: Options | null
  go: (key: PageKey) => void
  /** Cola del servidor (todas las páginas), refrescada sola mientras haya trabajo. */
  jobs: Job[]
  /** Mete o actualiza un trabajo en `jobs` sin esperar al siguiente sondeo. */
  trackJob: (job: Job) => void
  /** Pone `path` como imagen de entrada de esa página y navega a ella. */
  sendTo: (target: SendTarget, path: string) => void
  /** Imagen de entrada pendiente de cada página (la consumen las páginas). */
  inbox: Partial<Record<SendTarget, { path: string; n: number }>>
  /** Última imagen generada / sin fondo de la sesión (para "Usar la última"). */
  lastGenerated: string | null
  lastTransparent: string | null
  noteResult: (path: string, transparent: boolean) => void
  /** Plantillas de estilo/anatomía; Ajustes la sustituye al guardar. */
  library: StyleData | null
  setLibrary: (library: StyleData) => void
}

export const AppContext = createContext<AppState | null>(null)

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp fuera de AppContext')
  return ctx
}
