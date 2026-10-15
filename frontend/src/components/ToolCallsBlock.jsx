import { useState } from 'react'
import { ChevronDownIcon, WrenchIcon } from './icons'

// Shows the tools the model called for this answer (see backend/tools.py):
// what it asked for, and what the tool returned. Collapsed by default; while a
// tool runs, the header pulses.

function formatArgs(args) {
  const entries = Object.entries(args || {})
  if (entries.length === 0) return ''
  return entries.map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(', ')
}

function ToolCall({ call }) {
  const [open, setOpen] = useState(false)
  const running = call.status === 'running'
  const failed = call.status === 'error'
  const args = formatArgs(call.args)

  return (
    <div className="overflow-hidden rounded-bubble border border-line bg-bubble">
      <button
        onClick={() => setOpen((o) => !o)}
        className="focus-ring flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-[12px] text-muted transition hover:text-ink"
        aria-expanded={open}
      >
        <span className="flex min-w-0 items-center gap-1.5">
          {running ? (
            <span className="h-1.5 w-1.5 shrink-0 animate-dot-pulse rounded-full bg-muted" />
          ) : (
            <WrenchIcon width={13} height={13} className="shrink-0" />
          )}
          <span className="shrink-0 font-medium uppercase tracking-wide text-[11px]">
            {running ? 'Using tool' : failed ? 'Tool failed' : 'Used tool'}
          </span>
          <span className="truncate font-mono text-ink">
            {call.name}
            <span className="text-muted">({args})</span>
          </span>
        </span>
        {!running && (
          <ChevronDownIcon
            width={14}
            height={14}
            className="shrink-0"
            style={{
              transform: open ? 'none' : 'rotate(-90deg)',
              transition: 'transform 0.15s ease',
            }}
          />
        )}
      </button>
      {open && !running && (
        <div className="border-t border-line px-3 py-2 text-[12px]">
          <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted">
            The model asked for
          </div>
          <pre className="mb-2 whitespace-pre-wrap break-words font-mono text-ink">
            {call.name}({args})
          </pre>
          <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted">
            The tool returned
          </div>
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-ink">
            {call.result}
          </pre>
        </div>
      )}
    </div>
  )
}

export default function ToolCallsBlock({ calls }) {
  if (!calls || calls.length === 0) return null
  return (
    <div className="my-3 flex flex-col gap-1.5">
      {calls.map((c) => (
        <ToolCall key={c.id} call={c} />
      ))}
    </div>
  )
}
