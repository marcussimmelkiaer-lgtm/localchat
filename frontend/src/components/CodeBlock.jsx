import { useEffect, useRef, useState } from 'react'
import hljs from 'highlight.js/lib/common'
import { CopyIcon, CheckIcon } from './icons'

// A fenced code block: plain monospace while streaming, highlighted once the
// content settles (avoids O(n^2) re-highlighting per token). Copy button on hover.
export default function CodeBlock({ code, language, streaming }) {
  const ref = useRef(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el || streaming) return
    // Highlight after the message finishes streaming.
    el.removeAttribute('data-highlighted')
    el.className = language ? `hljs language-${language}` : 'hljs'
    el.textContent = code
    try {
      if (language && hljs.getLanguage(language)) {
        el.innerHTML = hljs.highlight(code, { language }).value
      } else {
        el.innerHTML = hljs.highlightAuto(code).value
      }
    } catch {
      el.textContent = code
    }
  }, [code, language, streaming])

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      setTimeout(() => setCopied(false), 1400)
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="group/code relative my-3.5 overflow-hidden rounded-bubble border border-line bg-bubble">
      <div className="flex items-center justify-between border-b border-line px-3 py-1.5">
        <span className="select-none text-[11px] font-medium uppercase tracking-wide text-muted">
          {language || 'code'}
        </span>
        <button
          onClick={onCopy}
          className="focus-ring flex items-center gap-1 rounded-control px-1.5 py-1 text-[11px] text-muted opacity-0 transition hover:bg-bubble-hover hover:text-ink group-hover/code:opacity-100"
          aria-label="Copy code"
        >
          {copied ? <CheckIcon width={13} height={13} /> : <CopyIcon width={13} height={13} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="scroll-thin overflow-x-auto px-4 py-3 text-[13px] leading-relaxed">
        {streaming ? (
          <code className="hljs font-mono">{code}</code>
        ) : (
          <code ref={ref} className="hljs font-mono" />
        )}
      </pre>
    </div>
  )
}
