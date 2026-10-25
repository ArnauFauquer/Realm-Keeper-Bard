import { CheckCircle, Cube, MagicWand, PaintBrush, Queue, Scissors, WarningCircle, X } from '@phosphor-icons/react'
import type { ReactNode } from 'react'
import { api, jobActive, type Job, type JobKind } from '../api'
import { JOB_PAGE, useApp } from '../appContext'
import { cx } from './ui'

const KIND_ICON: Record<JobKind, ReactNode> = {
  create: <PaintBrush size={15} />,
  transform: <MagicWand size={15} />,
  remove_bg: <Scissors size={15} />,
  mesh: <Cube size={15} />,
}

const RECENT = 4

function statusText(job: Job) {
  switch (job.status) {
    case 'running':
      return job.progress || 'Trabajando...'
    case 'queued':
      return `En cola · puesto ${job.position}`
    case 'done':
      return job.warning || 'Hecho'
    case 'error':
      return 'Error'
    case 'cancelled':
      return 'Cancelado'
  }
}

/** Cola global: lo que está en marcha, lo que espera y lo último terminado.
 *  Pulsar un trabajo lleva a la sección donde aparecen sus resultados. */
export function QueuePanel() {
  const { jobs, trackJob, go } = useApp()
  const active = jobs.filter(jobActive).sort((a, b) => {
    if (a.status !== b.status) return a.status === 'running' ? -1 : 1
    return a.created - b.created
  })
  const recent = jobs
    .filter((j) => !jobActive(j))
    .sort((a, b) => (b.finished ?? 0) - (a.finished ?? 0))
    .slice(0, RECENT)
  if (!active.length && !recent.length) return null

  const row = (job: Job) => {
    // la generación de imagen no se puede interrumpir a medias: en marcha solo se cancela el 3D
    const cancellable = job.status === 'queued' || (job.status === 'running' && job.kind === 'mesh')
    return (
      <li key={job.id} className="group flex items-start gap-2">
        <button
          type="button"
          onClick={() => go(JOB_PAGE[job.kind])}
          className="flex min-w-0 flex-1 items-start gap-2 rounded-[8px] px-1.5 py-1 text-left hover:bg-surface-2"
          title={job.label}
        >
          <span
            className={cx(
              'mt-0.5 shrink-0',
              job.status === 'running' && 'text-accent',
              job.status === 'queued' && 'text-muted',
              job.status === 'done' && 'text-ok',
              job.status === 'error' && 'text-danger',
              job.status === 'cancelled' && 'text-muted/60',
            )}
          >
            {job.status === 'done' ? (
              <CheckCircle size={15} />
            ) : job.status === 'error' ? (
              <WarningCircle size={15} />
            ) : (
              KIND_ICON[job.kind]
            )}
          </span>
          <span className="grid min-w-0">
            <span className={cx('truncate text-xs', jobActive(job) ? 'text-fg' : 'text-muted')}>{job.label}</span>
            <span
              className={cx(
                'truncate text-[11px]',
                job.status === 'running' ? 'text-accent' : job.status === 'error' ? 'text-danger' : 'text-muted/80',
              )}
            >
              {statusText(job)}
            </span>
          </span>
        </button>
        {cancellable && (
          <button
            type="button"
            aria-label="Cancelar"
            title={job.status === 'queued' ? 'Quitar de la cola' : 'Cancelar'}
            onClick={async () => trackJob(await api.cancel(job.id))}
            className="mt-1 inline-flex size-6 shrink-0 items-center justify-center rounded-[6px] text-muted hover:bg-danger/10 hover:text-danger"
          >
            <X size={13} />
          </button>
        )}
      </li>
    )
  }

  return (
    <div className="grid gap-2 rounded-2xl border border-line bg-bg p-3">
      <div className="flex items-center gap-2 px-0.5">
        <Queue size={16} className="text-muted" />
        <span className="text-sm font-medium text-fg">Cola</span>
        {active.length > 0 && (
          <span className="ml-auto rounded-full bg-accent-soft px-2 py-0.5 font-mono text-[11px] text-accent">
            {active.length}
          </span>
        )}
      </div>
      <ul className="scroll-thin grid max-h-[40dvh] gap-0.5 overflow-y-auto">
        {active.map(row)}
        {active.length > 0 && recent.length > 0 && <li className="mx-1.5 my-1 h-px bg-line" />}
        {recent.map(row)}
      </ul>
    </div>
  )
}
