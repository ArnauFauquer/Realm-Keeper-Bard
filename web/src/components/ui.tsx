// Primitivas de formulario y contenedores. Radios: controles rounded-[10px],
// paneles rounded-2xl, chips rounded-full.
import type { ButtonHTMLAttributes, ReactNode, TextareaHTMLAttributes } from 'react'
import { useId } from 'react'

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(' ')
}

export function Panel({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <section className={cx('rounded-2xl border border-line bg-surface shadow-panel', className)}>
      {children}
    </section>
  )
}

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'

export function Button({
  variant = 'secondary',
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type="button"
      {...props}
      className={cx(
        'inline-flex h-10 items-center justify-center gap-2 whitespace-nowrap rounded-[10px] px-4 text-sm font-medium',
        'transition-[background-color,border-color,color,transform] duration-200 ease-[cubic-bezier(0.16,1,0.3,1)]',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent',
        'active:translate-y-px disabled:pointer-events-none disabled:opacity-45',
        variant === 'primary' && 'bg-accent text-on-accent hover:brightness-110',
        variant === 'secondary' && 'border border-line bg-surface-2 text-fg hover:border-muted/60',
        variant === 'ghost' && 'text-muted hover:bg-surface-2 hover:text-fg',
        variant === 'danger' && 'border border-danger/40 text-danger hover:bg-danger/10',
        className,
      )}
    >
      {children}
    </button>
  )
}

export function IconButton({
  label,
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      {...props}
      className={cx(
        'inline-flex size-9 items-center justify-center rounded-[10px] text-muted transition-colors',
        'hover:bg-surface-2 hover:text-fg active:translate-y-px disabled:opacity-40 disabled:pointer-events-none',
        'focus-visible:outline-2 focus-visible:outline-accent',
        className,
      )}
    >
      {children}
    </button>
  )
}

export function Field({
  label,
  hint,
  children,
  htmlFor,
}: {
  label: string
  hint?: ReactNode
  children: ReactNode
  htmlFor?: string
}) {
  return (
    <div className="grid gap-2">
      <label htmlFor={htmlFor} className="text-sm font-medium text-fg">
        {label}
      </label>
      {children}
      {hint && <p className="text-xs leading-relaxed text-muted">{hint}</p>}
    </div>
  )
}

export function TextArea({
  label,
  hint,
  minRows = 3,
  className,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; hint?: ReactNode; minRows?: number }) {
  const id = useId()
  return (
    <Field label={label} hint={hint} htmlFor={id}>
      <textarea
        id={id}
        rows={minRows}
        {...props}
        style={{ minHeight: `${minRows * 1.6 + 1.5}rem` }}
        className={cx(
          'scroll-thin w-full resize-y rounded-[10px] border border-line bg-bg px-3 py-2.5 text-sm leading-relaxed text-fg',
          'placeholder:text-muted/80 focus:border-accent focus:outline-none focus:ring-3 focus:ring-accent-soft',
          className,
        )}
      />
    </Field>
  )
}

export function Toggle({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label: string
  hint?: string
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="group flex w-full items-start gap-3 rounded-[10px] py-1 text-left focus-visible:outline-2 focus-visible:outline-accent"
    >
      <span
        className={cx(
          'relative mt-0.5 inline-flex h-5 w-9 shrink-0 rounded-full border transition-colors duration-200',
          checked ? 'border-accent bg-accent' : 'border-line bg-surface-2',
        )}
      >
        <span
          className={cx(
            'absolute top-0.5 size-3.5 rounded-full transition-transform duration-200 ease-[cubic-bezier(0.16,1,0.3,1)]',
            checked ? 'translate-x-[18px] bg-on-accent' : 'translate-x-0.5 bg-muted',
          )}
        />
      </span>
      <span className="grid gap-0.5">
        <span className="text-sm text-fg">{label}</span>
        {hint && <span className="text-xs text-muted">{hint}</span>}
      </span>
    </button>
  )
}

export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
  stacked = false,
}: {
  value: T
  onChange: (v: T) => void
  options: { value: T; label: string; icon?: ReactNode }[]
  label: string
  /** Icono encima del texto: cabe en columnas estrechas sin recortar etiquetas. */
  stacked?: boolean
}) {
  return (
    <div className="grid gap-2">
      <span className="text-sm font-medium text-fg">{label}</span>
      <div
        role="radiogroup"
        aria-label={label}
        className="grid gap-1 rounded-[12px] border border-line bg-bg p-1"
        style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}
      >
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={value === o.value}
            onClick={() => onChange(o.value)}
            className={cx(
              'flex min-w-0 items-center justify-center rounded-[8px] px-2 text-[13px] transition-colors duration-200',
              stacked ? 'h-14 flex-col gap-1' : 'h-9 gap-1.5',
              'focus-visible:outline-2 focus-visible:outline-accent',
              value === o.value ? 'bg-surface text-fg shadow-panel ring-1 ring-line' : 'text-muted hover:text-fg',
            )}
          >
            {o.icon}
            <span className="truncate">{o.label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

export function NumberInput({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
}: {
  label: string
  value: number
  onChange: (v: number) => void
  min: number
  max: number
  step?: number
}) {
  const id = useId()
  return (
    <Field label={label} htmlFor={id}>
      <input
        id={id}
        type="number"
        inputMode="numeric"
        value={Number.isFinite(value) ? value : ''}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(e.target.valueAsNumber)}
        className="h-10 w-full rounded-[10px] border border-line bg-bg px-3 font-mono text-sm text-fg focus:border-accent focus:outline-none focus:ring-3 focus:ring-accent-soft"
      />
    </Field>
  )
}

export function TextInput({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (v: string) => void
}) {
  const id = useId()
  return (
    <Field label={label} htmlFor={id}>
      <input
        id={id}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-10 w-full rounded-[10px] border border-line bg-bg px-3 text-sm text-fg focus:border-accent focus:outline-none focus:ring-3 focus:ring-accent-soft"
      />
    </Field>
  )
}

export function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
}) {
  const id = useId()
  return (
    <Field label={label} htmlFor={id}>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-10 w-full rounded-[10px] border border-line bg-bg px-3 text-sm text-fg focus:border-accent focus:outline-none focus:ring-3 focus:ring-accent-soft"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </Field>
  )
}

export function PageHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <header className="mb-6 grid gap-1.5">
      <h1 className="text-2xl font-semibold tracking-tight text-fg md:text-[28px]">{title}</h1>
      <p className="max-w-[65ch] text-sm leading-relaxed text-muted">{subtitle}</p>
    </header>
  )
}
