import { useEffect, useState } from 'react'
import { CheckIcon, CloseIcon, TrashIcon } from './icons'

// Modal listing the curated catalog + any custom-downloaded models. Per row:
// Active badge / Use (switch) / Download / progress while a task targets it, and
// a delete action (hidden for the active model). Bottom: a custom huggingface:
// spec field. Driven entirely by the useModelManager hook passed in as `mgr`.
export default function ModelPicker({ mgr, onClose }) {
  const { data, task, busy, actionError, clearActionError, download, switchTo, remove } = mgr
  const [spec, setSpec] = useState('')
  const [confirmDel, setConfirmDel] = useState(null) // path pending delete confirm

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const catalog = data?.catalog || []
  // Custom downloads = cached files not represented in the curated catalog.
  const customs = (data?.cached || []).filter((c) => !c.in_catalog)
  const target = task?.target

  const isTarget = (row) =>
    busy && (target === row.spec || (row.path && target === row.path))

  // A first-time custom download (typed spec) has no row to hang progress on —
  // it isn't a catalog entry and isn't in `cached` until the download finishes.
  // Detect that in-flight task and render a synthetic progress row for it.
  const matchesRow =
    !!target &&
    (catalog.some((r) => target === r.spec || target === r.path) ||
      customs.some((c) => target === c.path))
  const orphanTask = busy && !!target && !matchesRow
  const orphanTitle = target
    ? String(target).split(/[\\/]/).pop().replace(/\.gguf$/i, '')
    : 'Model'

  const onUse = (path) => switchTo(path)
  // A vision model needs its mmproj too, and shouldn't become the persistent
  // default (image turns borrow it automatically) — download both, no switch.
  const onGet = (row) =>
    row.projection ? download(row.spec, false, [row.projection]) : download(row.spec, true)
  const onDelete = (path) => {
    setConfirmDel(null)
    remove(path)
  }

  const submitCustom = (e) => {
    e.preventDefault()
    const s = spec.trim()
    if (s && !busy) download(s, true).then((ok) => ok && setSpec(''))
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/20 p-4"
      onMouseDown={onClose}
    >
      <div
        className="flex max-h-[80vh] w-full max-w-[440px] flex-col overflow-hidden rounded-card border border-line bg-ground shadow-xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <h2 className="text-[14px] font-semibold text-ink">Models</h2>
          <button
            onClick={onClose}
            className="focus-ring rounded-control p-1 text-muted transition hover:bg-hover hover:text-ink"
            aria-label="Close"
          >
            <CloseIcon width={16} height={16} />
          </button>
        </div>

        <div className="scroll-thin flex-1 overflow-y-auto px-3 py-3">
          {(actionError || task?.status === 'error') && (
            <div className="mb-3 flex items-start justify-between gap-2 rounded-control border border-line bg-bubble px-3 py-2 text-[12.5px] text-muted">
              <span>{actionError || task?.error}</span>
              {actionError && (
                <button
                  onClick={clearActionError}
                  className="shrink-0 text-muted hover:text-ink"
                  aria-label="Dismiss"
                >
                  <CloseIcon width={13} height={13} />
                </button>
              )}
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            {orphanTask && (
              <ModelRow
                title={orphanTitle}
                subtitle="Custom download"
                active={false}
                downloaded={false}
                targeted
                task={task}
                busy={busy}
                confirming={false}
                onUse={() => {}}
                onGet={() => {}}
                onAskDelete={() => {}}
                onCancelDelete={() => {}}
                onConfirmDelete={() => {}}
              />
            )}
            {catalog.map((row) => (
              <ModelRow
                key={row.id}
                title={row.name}
                subtitle={`${row.quant} · ${row.size_gb} GB · ${row.note}`}
                active={row.active}
                downloaded={row.downloaded}
                targeted={isTarget(row)}
                task={task}
                busy={busy}
                confirming={confirmDel === row.path}
                onUse={() => onUse(row.path)}
                onGet={() => onGet(row)}
                onAskDelete={() => setConfirmDel(row.path)}
                onCancelDelete={() => setConfirmDel(null)}
                onConfirmDelete={() => onDelete(row.path)}
              />
            ))}

            {customs.length > 0 && (
              <div className="mt-2 px-1 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wide text-muted">
                Other downloaded
              </div>
            )}
            {customs.map((c) => (
              <ModelRow
                key={c.path}
                title={c.name.replace(/\.gguf$/i, '')}
                subtitle={`${(c.size_bytes / 1e9).toFixed(1)} GB`}
                active={c.active}
                downloaded
                targeted={busy && target === c.path}
                task={task}
                busy={busy}
                confirming={confirmDel === c.path}
                onUse={() => onUse(c.path)}
                onGet={() => {}}
                onAskDelete={() => setConfirmDel(c.path)}
                onCancelDelete={() => setConfirmDel(null)}
                onConfirmDelete={() => onDelete(c.path)}
              />
            ))}
          </div>
        </div>

        <form onSubmit={submitCustom} className="border-t border-line px-3 py-3">
          <label className="mb-1.5 block px-1 text-[11px] font-medium uppercase tracking-wide text-muted">
            Download from Hugging Face
          </label>
          <div className="flex gap-2">
            <input
              value={spec}
              onChange={(e) => setSpec(e.target.value)}
              placeholder="Qwen/Qwen3-0.6B"
              disabled={busy}
              className="focus-ring min-w-0 flex-1 rounded-control border border-line bg-ground px-3 py-2 text-[12.5px] text-ink placeholder:text-muted disabled:opacity-60"
            />
            <button
              type="submit"
              disabled={busy || !spec.trim()}
              className="focus-ring shrink-0 rounded-control bg-ink px-3 py-2 text-[12.5px] font-medium text-ground transition hover:opacity-90 disabled:cursor-not-allowed disabled:bg-line disabled:text-muted"
            >
              Download
            </button>
          </div>
          <p className="mt-1.5 px-1 text-[11px] text-muted">
            Paste a repo id (<span className="text-ink">Qwen/Qwen3-0.6B</span>), add{' '}
            <span className="text-ink">:Q5_K_M</span> to pick a quant, or paste a full{' '}
            <span className="text-ink">owner/repo/file.gguf</span> / Hugging Face URL.
          </p>
        </form>
      </div>
    </div>
  )
}

function ModelRow({
  title,
  subtitle,
  active,
  downloaded,
  targeted,
  task,
  busy,
  confirming,
  onUse,
  onGet,
  onAskDelete,
  onCancelDelete,
  onConfirmDelete,
}) {
  return (
    <div className="flex items-center gap-3 rounded-control border border-line px-3 py-2.5">
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-medium text-ink">{title}</div>
        <div className="truncate text-[11.5px] text-muted">{subtitle}</div>
        {targeted && (
          <div className="mt-1.5">
            <div className="h-1 w-full overflow-hidden rounded-full bg-bubble-hover">
              <div
                className="h-full bg-ink transition-all"
                style={{
                  width:
                    task.status === 'downloading'
                      ? `${Math.round((task.fraction || 0) * 100)}%`
                      : '100%',
                }}
              />
            </div>
            <div className="mt-1 text-[11px] text-muted">
              {task.status === 'downloading'
                ? `Downloading… ${Math.round((task.fraction || 0) * 100)}%`
                : 'Loading…'}
            </div>
          </div>
        )}
      </div>

      {!targeted && (
        <div className="flex shrink-0 items-center gap-1.5">
          {active ? (
            <span className="flex items-center gap-1 rounded-control bg-bubble px-2 py-1 text-[11.5px] font-medium text-ink">
              <CheckIcon width={13} height={13} /> Active
            </span>
          ) : downloaded ? (
            <button
              onClick={onUse}
              disabled={busy}
              className="focus-ring rounded-control border border-line px-2.5 py-1 text-[12px] font-medium text-ink transition hover:bg-hover disabled:opacity-50"
            >
              Use
            </button>
          ) : (
            <button
              onClick={onGet}
              disabled={busy}
              className="focus-ring rounded-control bg-ink px-2.5 py-1 text-[12px] font-medium text-ground transition hover:opacity-90 disabled:opacity-50"
            >
              Download
            </button>
          )}

          {downloaded && !active && (
            confirming ? (
              <div className="flex items-center gap-1">
                <button
                  onClick={onConfirmDelete}
                  disabled={busy}
                  className="focus-ring rounded-control px-2 py-1 text-[11.5px] font-medium text-ink hover:bg-hover disabled:opacity-50"
                >
                  Delete
                </button>
                <button
                  onClick={onCancelDelete}
                  className="focus-ring rounded-control px-2 py-1 text-[11.5px] text-muted hover:bg-hover"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                onClick={onAskDelete}
                disabled={busy}
                className="focus-ring rounded-control p-1.5 text-muted transition hover:bg-hover hover:text-ink disabled:opacity-50"
                aria-label={`Delete ${title}`}
                title="Delete from disk"
              >
                <TrashIcon width={15} height={15} />
              </button>
            )
          )}
        </div>
      )}
    </div>
  )
}
