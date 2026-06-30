import { useEffect, useRef, useState } from 'react'
import { TrashIcon, PencilIcon } from './icons'

export default function ConversationItem({ conv, active, onSelect, onRename, onDelete }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(conv.title)
  const inputRef = useRef(null)

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus()
      inputRef.current?.select()
    }
  }, [editing])

  const startEdit = (e) => {
    e.stopPropagation()
    setDraft(conv.title)
    setEditing(true)
  }

  const commit = () => {
    const t = draft.trim()
    setEditing(false)
    if (t && t !== conv.title) onRename(conv.id, t)
  }

  if (editing) {
    return (
      <div className={`rounded-control px-2 py-1.5 ${active ? 'bg-bubble' : 'bg-hover'}`}>
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              commit()
            } else if (e.key === 'Escape') {
              setEditing(false)
            }
          }}
          className="w-full bg-transparent text-[13px] text-ink focus:outline-none"
        />
      </div>
    )
  }

  return (
    <div
      onClick={() => onSelect(conv.id)}
      className={`group/item flex cursor-pointer items-center gap-1 rounded-control px-2 py-1.5 text-[13px] ${
        active ? 'bg-bubble text-ink' : 'text-ink hover:bg-hover'
      }`}
    >
      <span className="flex-1 truncate">{conv.title || 'New chat'}</span>
      <button
        onClick={startEdit}
        className="focus-ring rounded p-1 text-muted opacity-0 transition hover:text-ink group-hover/item:opacity-100"
        aria-label="Rename conversation"
      >
        <PencilIcon width={14} height={14} />
      </button>
      <button
        onClick={(e) => {
          e.stopPropagation()
          onDelete(conv.id)
        }}
        className="focus-ring rounded p-1 text-muted opacity-0 transition hover:text-ink group-hover/item:opacity-100"
        aria-label="Delete conversation"
      >
        <TrashIcon width={14} height={14} />
      </button>
    </div>
  )
}
