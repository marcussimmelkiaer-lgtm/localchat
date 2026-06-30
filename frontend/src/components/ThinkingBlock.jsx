import { useState } from 'react'
import Markdown from './Markdown'
import { ChevronDownIcon } from './icons'

// Renders a reasoning model's <think> content in a distinct, collapsible box
// (code-block styling) so it reads clearly as thought process, not the answer.
export default function ThinkingBlock({ text, streaming }) {
  const [open, setOpen] = useState(true)
  return (
    <div className="my-3 overflow-hidden rounded-bubble border border-line bg-bubble">
      <button
        onClick={() => setOpen((o) => !o)}
        className="focus-ring flex w-full items-center justify-between px-3 py-1.5 text-[11px] font-medium uppercase tracking-wide text-muted transition hover:text-ink"
        aria-expanded={open}
      >
        <span className="flex items-center gap-1.5">
          {streaming && (
            <span className="h-1.5 w-1.5 animate-dot-pulse rounded-full bg-muted" />
          )}
          {streaming ? 'Thinking…' : 'Thought process'}
        </span>
        <ChevronDownIcon
          width={14}
          height={14}
          style={{
            transform: open ? 'none' : 'rotate(-90deg)',
            transition: 'transform 0.15s ease',
          }}
        />
      </button>
      {open && (
        <div className="thinking-body border-t border-line px-3 py-2">
          <Markdown content={text} streaming={streaming} />
        </div>
      )}
    </div>
  )
}
