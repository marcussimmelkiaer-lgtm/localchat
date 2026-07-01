import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowUpIcon, StopIcon, PaperclipIcon, FileIcon, CloseIcon } from './icons'

const MAX_HEIGHT = 200 // ~8 lines, then the textarea scrolls internally
const ACCEPT = [
  '.csv', '.pdf', '.xlsx', '.xls', '.docx',
  '.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp',
  'text/csv',
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'image/*',
].join(',')

function fileKey(f) {
  return `${f.name}:${f.size}:${f.lastModified}`
}

// Chip preview: a thumbnail for images (via a revoked object URL), else an icon.
function FileThumb({ file }) {
  const url = useMemo(
    () => (file.type?.startsWith('image/') ? URL.createObjectURL(file) : null),
    [file]
  )
  useEffect(() => () => url && URL.revokeObjectURL(url), [url])
  if (url) return <img src={url} alt="" className="h-8 w-8 shrink-0 rounded object-cover" />
  return <FileIcon width={14} height={14} className="shrink-0 text-muted" />
}

export default function Composer({ onSend, onStop, isStreaming, disabled, placeholder, autoFocus }) {
  const [value, setValue] = useState('')
  const [files, setFiles] = useState([])
  const taRef = useRef(null)
  const fileRef = useRef(null)
  const composingRef = useRef(false)

  const grow = () => {
    const el = taRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, MAX_HEIGHT) + 'px'
    el.style.overflowY = el.scrollHeight > MAX_HEIGHT ? 'auto' : 'hidden'
  }

  useEffect(grow, [value])
  useEffect(() => {
    if (autoFocus) taRef.current?.focus()
  }, [autoFocus])

  const addFiles = (incoming) => {
    const picked = Array.from(incoming || [])
    if (!picked.length) return
    setFiles((prev) => {
      const seen = new Set(prev.map(fileKey))
      return [...prev, ...picked.filter((f) => !seen.has(fileKey(f)))]
    })
  }

  const removeFile = (key) => setFiles((prev) => prev.filter((f) => fileKey(f) !== key))

  const submit = () => {
    const text = value.trim()
    if ((!text && files.length === 0) || isStreaming || disabled) return
    onSend(text, files)
    setValue('')
    setFiles([])
  }

  const onKeyDown = (e) => {
    if (e.key === 'Escape' && isStreaming) {
      e.preventDefault()
      onStop()
      return
    }
    if (e.key === 'Enter' && !e.shiftKey && !composingRef.current) {
      e.preventDefault()
      submit()
    }
  }

  const canSend = (value.trim().length > 0 || files.length > 0) && !disabled

  return (
    <div className="rounded-card border border-line bg-ground shadow-composer">
      {files.length > 0 && (
        <div className="flex flex-wrap gap-2 px-3 pt-3">
          {files.map((f) => {
            const key = fileKey(f)
            return (
              <div
                key={key}
                className="flex items-center gap-1.5 rounded-control border border-line bg-bubble py-1 pl-1.5 pr-1 text-[12px] text-ink"
              >
                <FileThumb file={f} />
                <span className="max-w-[180px] truncate">{f.name}</span>
                <button
                  onClick={() => removeFile(key)}
                  className="focus-ring flex h-5 w-5 items-center justify-center rounded-full text-muted hover:bg-hover hover:text-ink"
                  aria-label={`Remove ${f.name}`}
                >
                  <CloseIcon width={12} height={12} />
                </button>
              </div>
            )
          })}
        </div>
      )}
      <div className="flex items-end gap-2 px-3 py-2.5">
        <input
          ref={fileRef}
          type="file"
          accept={ACCEPT}
          multiple
          className="hidden"
          onChange={(e) => {
            addFiles(e.target.files)
            e.target.value = ''
          }}
        />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={disabled}
          className="focus-ring flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-muted transition hover:bg-hover hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
          aria-label="Attach files"
          title="Attach a file (CSV, PDF, Excel, Word, or an image)"
        >
          <PaperclipIcon width={18} height={18} />
        </button>
        <textarea
          ref={taRef}
          rows={1}
          value={value}
          disabled={disabled}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          onCompositionStart={() => (composingRef.current = true)}
          onCompositionEnd={() => (composingRef.current = false)}
          placeholder={placeholder || 'Message…'}
          className="scroll-thin max-h-[200px] flex-1 resize-none bg-transparent px-1 py-1.5 text-[15px] leading-relaxed text-ink placeholder:text-muted focus:outline-none disabled:opacity-60"
        />
        {isStreaming ? (
          <button
            onClick={onStop}
            className="focus-ring flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ink text-ground transition hover:opacity-90"
            aria-label="Stop generating"
            title="Stop (Esc)"
          >
            <StopIcon width={18} height={18} />
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={!canSend}
            className="focus-ring flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ink text-ground transition hover:opacity-90 disabled:cursor-not-allowed disabled:bg-line disabled:text-muted"
            aria-label="Send message"
          >
            <ArrowUpIcon width={18} height={18} />
          </button>
        )}
      </div>
    </div>
  )
}
