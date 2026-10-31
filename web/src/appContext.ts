import { createContext, useContext } from 'react'
import type { Job, JobKind, Options, StyleData } from './api'

export type PageKey = 'create' | 'transform' | 'remove_bg' | 'model_3d' | 'library' | 'settings'
export type SendTarget = 'transform' | 'remove_bg' | 'model_3d'

/** Page from which each job type is launched. */
export const JOB_PAGE: Record<JobKind, PageKey> = {
  create: 'create',
  transform: 'transform',
  remove_bg: 'remove_bg',
  mesh: 'model_3d',
}

export interface AppState {
  options: Options | null
  go: (key: PageKey) => void
  /** Server queue (all pages), refreshed automatically while there is work. */
  jobs: Job[]
  /** Mete o actualiza un trabajo en `jobs` sin esperar al siguiente sondeo. */
  trackJob: (job: Job) => void
  /** Set `path` as that page's input image and navigate to it. */
  sendTo: (target: SendTarget, path: string) => void
  /** Pending input image for each page (consumed by the pages). */
  inbox: Partial<Record<SendTarget, { path: string; n: number }>>
  /** Last generated / background-removed image of the session (for "Use the last one"). */
  lastGenerated: string | null
  lastTransparent: string | null
  noteResult: (path: string, transparent: boolean) => void
  /** Style/anatomy templates; Settings replaces it on save. */
  library: StyleData | null
  setLibrary: (library: StyleData) => void
}

export const AppContext = createContext<AppState | null>(null)

export function useApp() {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp outside AppContext')
  return ctx
}
