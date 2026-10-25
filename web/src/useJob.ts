import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, jobActive, type Job, type ResultItem } from './api'
import { useApp } from './appContext'

/** Trabajos lanzados desde una página. Se pueden encolar varios: el servidor los
 *  ejecuta en orden y `onResult` recibe cada resultado nuevo en cuanto aparece
 *  (las variantes 3D llegan de una en una). */
export function useJob(onResult: (item: ResultItem) => void) {
  const { jobs, trackJob } = useApp()
  const [mine, setMine] = useState<string[]>([])
  const [startError, setStartError] = useState('')
  const seen = useRef<Record<string, number>>({})
  const onResultRef = useRef(onResult)
  onResultRef.current = onResult

  const myJobs = useMemo(
    () => mine.map((id) => jobs.find((j) => j.id === id)).filter((j): j is Job => !!j),
    [mine, jobs],
  )

  useEffect(() => {
    for (const job of myJobs) {
      for (const item of job.results.slice(seen.current[job.id] ?? 0)) onResultRef.current(item)
      seen.current[job.id] = job.results.length
    }
  }, [myJobs])

  const active = myJobs.find((j) => j.status === 'running') ?? null
  const queued = myJobs.filter((j) => j.status === 'queued')
  const latest = [...myJobs].reverse().find((j) => !jobActive(j)) ?? null
  const latestStarted = myJobs.at(-1)

  let progress = ''
  if (active) progress = (active.progress || 'Trabajando...') + (queued.length ? ` · ${queued.length} más en cola` : '')
  else if (queued.length) progress = `En cola · puesto ${queued[0].position}` + (queued.length > 1 ? ` (+${queued.length - 1})` : '')

  const start = useCallback(
    async (launch: () => Promise<Job>) => {
      setStartError('')
      try {
        const job = await launch()
        trackJob(job)
        setMine((prev) => [...prev, job.id])
      } catch (e) {
        setStartError((e as Error).message)
      }
    },
    [trackJob],
  )

  const cancel = useCallback(async () => {
    if (active) trackJob(await api.cancel(active.id))
  }, [active, trackJob])

  // el error/aviso solo se enseña si es del último trabajo lanzado
  const shown = latest && latest === latestStarted ? latest : null
  return {
    /** Hay algo en marcha o en cola desde esta página. */
    running: !!active || queued.length > 0,
    active,
    queued: queued.length,
    progress,
    since: active?.started ?? undefined,
    latest: shown,
    start,
    cancel,
    error: startError || (shown?.status === 'error' ? shown.error : ''),
  }
}

/** Segundos transcurridos mientras `active` es true. */
export function useElapsed(active: boolean, since?: number) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [active])
  return active && since ? Math.max(0, Math.round(now / 1000 - since)) : 0
}
