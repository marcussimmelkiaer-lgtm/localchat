import { useState } from 'react'
import Markdown from './Markdown'
import ThinkingBlock from './ThinkingBlock'
import TokensPerSec from './TokensPerSec'
import { CopyIcon, CheckIcon, RegenerateIcon, FileIcon } from './icons'

function AttachmentChips({ attachments, messageId }) {
  if (!attachments || attachments.length === 0) return null
  return (
    <div className="mb-1.5 flex flex-wrap justify-end gap-2">
      {attachments.map((a, i) => {
        const isImage = a.is_image || (a.mime || '').startsWith('image/')
        // Live: the local previewUrl. Reload: re-served by message id + index.
        const src = a.previewUrl || (isImage && messageId ? `/api/attachments/${messageId}/${i}` : null)
        if (isImage && src) {
          return (
            <img
              key={`${a.name}:${i}`}
              src={src}
              alt={a.name}
              title={a.name}
              className="max-h-44 max-w-[220px] rounded-card border border-line object-cover"
            />
          )
        }
        return (
          <div
            key={`${a.name}:${i}`}
            className="flex items-center gap-1.5 rounded-control border border-line bg-ground px-2 py-1 text-[12px] text-ink"
            title={a.name}
          >
            <FileIcon width={14} height={14} className="shrink-0 text-muted" />
            <span className="max-w-[200px] truncate">{a.name}</span>
          </div>
        )
      })}
    </div>
  )
}

// Split a reasoning model's output into its <think> block and the answer.
// During streaming the closing tag may not have arrived yet (thinkingDone=false).
function splitThinking(content) {
  const open = content.indexOf('<think>')
  if (open === -1) return { thinking: null, answer: content, thinkingDone: true }
  const pre = content.slice(0, open)
  const rest = content.slice(open + 7)
  const close = rest.indexOf('</think>')
  if (close === -1) return { thinking: rest, answer: pre, thinkingDone: false }
  return { thinking: rest.slice(0, close), answer: pre + rest.slice(close + 8), thinkingDone: true }
}

function LoadingDots() {
  return (
    <span className="inline-flex items-center gap-1 py-2" aria-label="Generating">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 rounded-full bg-muted animate-dot-pulse"
          style={{ animationDelay: `${i * 0.16}s` }}
        />
      ))}
    </span>
  )
}

function HoverActions({ onCopy, copied, onRegenerate, canRegenerate }) {
  return (
    <div className="mt-1 flex items-center gap-1 opacity-0 transition-opacity group-hover/msg:opacity-100 focus-within:opacity-100">
      <button
        onClick={onCopy}
        className="focus-ring flex items-center gap-1 rounded-control px-1.5 py-1 text-[12px] text-muted hover:bg-hover hover:text-ink"
        aria-label="Copy message"
      >
        {copied ? <CheckIcon width={14} height={14} /> : <CopyIcon width={14} height={14} />}
      </button>
      {canRegenerate && (
        <button
          onClick={onRegenerate}
          className="focus-ring flex items-center gap-1 rounded-control px-1.5 py-1 text-[12px] text-muted hover:bg-hover hover:text-ink"
          aria-label="Regenerate response"
        >
          <RegenerateIcon width={14} height={14} />
        </button>
      )}
    </div>
  )
}

export default function Message({ message, isLast, onRegenerate }) {
  const [copied, setCopied] = useState(false)

  if (message.role === 'user') {
    return (
      <div className="group/msg flex animate-fade-in justify-end">
        <div className="flex max-w-[85%] flex-col items-end">
          <AttachmentChips attachments={message.attachments} messageId={message.id} />
          {message.content && (
            <div className="whitespace-pre-wrap break-words rounded-bubble bg-bubble px-4 py-2.5 text-[15px] leading-relaxed text-ink">
              {message.content}
            </div>
          )}
        </div>
      </div>
    )
  }

  // assistant
  const streaming = message.status === 'streaming'
  const { thinking, answer, thinkingDone } = splitThinking(message.content || '')
  const showLoading = streaming && !message.content
  const answerCaret = streaming && (thinking === null || thinkingDone)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(answer || message.content || '')
      setCopied(true)
      setTimeout(() => setCopied(false), 1400)
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="group/msg flex animate-fade-in gap-3">
      <div className="mt-1 h-6 w-6 shrink-0 rounded-full border border-line bg-ground" aria-hidden>
        <div className="m-[7px] h-2.5 w-2.5 rounded-full bg-ink" />
      </div>
      <div className="min-w-0 flex-1">
        {showLoading ? (
          <LoadingDots />
        ) : (
          <>
            {thinking !== null && (
              <ThinkingBlock text={thinking} streaming={streaming && !thinkingDone} />
            )}
            {(thinking === null || thinkingDone || answer) && (
              <div className={answerCaret ? 'caret' : undefined}>
                <Markdown content={answer} streaming={streaming} />
              </div>
            )}
          </>
        )}

        {message.status === 'error' && (
          <div className="mt-2 rounded-control border border-line bg-bubble px-3 py-2 text-[13px] text-muted">
            {typeof message.error === 'string' && message.error
              ? message.error
              : 'Something went wrong while generating.'}
          </div>
        )}

        {!streaming && (
          <>
            <TokensPerSec stats={message.stats} stopped={message.status === 'stopped'} />
            {message.content && (
              <HoverActions
                onCopy={copy}
                copied={copied}
                onRegenerate={onRegenerate}
                canRegenerate={isLast && message.status !== 'error'}
              />
            )}
          </>
        )}
      </div>
    </div>
  )
}
