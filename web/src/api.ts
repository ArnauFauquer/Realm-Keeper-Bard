// Cliente de la API de app/server.py. Las imágenes viajan como rutas relativas
// a la raíz del proyecto ("generated_images/x.png").

export type Category = 'personaje' | 'fondo' | 'objeto' | 'mapa'

export interface ImageItem {
  kind: 'image'
  path: string
  name: string
  width?: number
  height?: number
  mtime?: number
  role?: 'prepared'
}

export interface MeshItem {
  kind: 'mesh'
  name: string
  glb: string
  stl: string | null
  previews: string[]
  model?: string
  quality?: string
  seed?: number
  faces?: number
  size_mm?: number[]
  watertight?: boolean
  filled?: boolean
  seconds?: number
  mtime?: number
}

export type ResultItem = ImageItem | MeshItem

export type JobKind = 'create' | 'transform' | 'remove_bg' | 'mesh'

export interface Job {
  id: string
  kind: JobKind
  /** Resumen corto para la cola ("personaje: una rata herrera..."). */
  label: string
  status: 'queued' | 'running' | 'done' | 'error' | 'cancelled'
  progress: string
  results: ResultItem[]
  error: string
  warning: string
  created: number
  started: number | null
  finished: number | null
  /** Puesto en su fila mientras está en cola (1 = el siguiente). */
  position: number
}

export const jobActive = (job: Job) => job.status === 'queued' || job.status === 'running'

export interface Option {
  label: string
  value: string
}

export interface Options {
  categories: Category[]
  mesh_models: Option[]
  mesh_qualities: Option[]
  mesh_prepare_modes: Option[]
  mesh_ready: boolean
}

export interface EngineInfo {
  status: 'stopped' | 'starting' | 'ready' | 'error'
  message: string
}

export interface StylePreset {
  id: string
  name: string
  style_prompt: string
  constraints: string
}

export interface SpeciesPreset {
  id: string
  name: string
  species_prompt: string
  species_ref: string
  species_ref_resolved?: string | null
}

/** Plantillas de estilo y de anatomía + ajustes comunes a todas. */
export interface StyleData {
  styles: StylePreset[]
  species: SpeciesPreset[]
  active_style: string
  active_species: string
  pov: Record<Category, string>
  style_3d: string
  map_style: string
  map_constraints: string
}

export type LibraryFolder = 'images' | 'transparent' | 'references' | 'models'

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      /* respuesta sin JSON */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const fileUrl = (path: string) => `/files/${path.split('/').map(encodeURIComponent).join('/')}`
export const thumbUrl = (path: string, size = 360) =>
  `/thumbs/${path.split('/').map(encodeURIComponent).join('/')}?s=${size}`

export const api = {
  engine: () => request<EngineInfo>('/api/engine'),
  startEngine: () => request<EngineInfo>('/api/engine/start', { method: 'POST' }),
  options: () => request<Options>('/api/options'),
  last: () => request<{ generated: string | null; transparent: string | null }>('/api/last'),
  create: (body: { category: Category; description: string; style_id: string; species_id: string; remove_bg: boolean }) =>
    request<Job>('/api/create', json('POST', body)),
  transform: (body: {
    reference: string
    is_map: boolean
    extra: string
    style_id: string
    species_id: string
    remove_bg: boolean
  }) => request<Job>('/api/transform', json('POST', body)),
  removeBg: (source: string) => request<Job>('/api/remove-bg', json('POST', { source })),
  mesh: (body: {
    source: string
    model: string
    quality: string
    prepare: string
    expression: string
    height_mm: number
    faces_k: number
    seed: number
    variants: number
  }) => request<Job>('/api/mesh', json('POST', body)),
  jobs: () => request<Job[]>('/api/jobs'),
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  cancel: (id: string) => request<Job>(`/api/jobs/${id}/cancel`, { method: 'POST' }),
  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<ImageItem>('/api/uploads', { method: 'POST', body: form })
  },
  library: (folder: LibraryFolder, offset = 0, limit = 60) =>
    request<{ items: ResultItem[]; total: number }>(`/api/library?folder=${folder}&offset=${offset}&limit=${limit}`),
  open: (path: string) => request<{ ok: boolean }>('/api/open', json('POST', { path })),
  style: () => request<StyleData>('/api/style'),
  saveStyle: (data: StyleData) => request<StyleData>('/api/style', json('PUT', data)),
}
