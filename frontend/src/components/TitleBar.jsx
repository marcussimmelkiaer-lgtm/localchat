import { useEffect, useState } from 'react'
import { MinimizeIcon, CloseIcon, FullscreenIcon, ExitFullscreenIcon } from './icons'

// Custom title bar for the frameless native window: a draggable strip with
// fullscreen + minimize + close. Each button enqueues a command through the
// js_api bridge; the actual window op runs on the webview worker thread.
// Fullscreen swaps the window bounds via SetWindowPos (it never touches
// WindowState/FormBorderStyle/DWM, which crash this WebView2 build — see
// backend/main.py _control_loop). Only renders inside the pywebview app.
const call = (method) => {
  try {
    window.pywebview?.api?.[method]?.()
  } catch {
    /* ignore */
  }
}

export default function TitleBar() {
  const [inApp, setInApp] = useState(
    typeof window !== 'undefined' && !!window.pywebview?.api
  )
  const [isFull, setIsFull] = useState(false)

  useEffect(() => {
    const check = () => setInApp(!!window.pywebview?.api)
    window.addEventListener('pywebviewready', check)
    const t = setTimeout(check, 400)
    return () => {
      window.removeEventListener('pywebviewready', check)
      clearTimeout(t)
    }
  }, [])

  // Esc leaves fullscreen (matches the native fullscreen convention).
  useEffect(() => {
    if (!isFull) return
    const onKey = (e) => {
      if (e.key === 'Escape') {
        call('toggle_fullscreen')
        setIsFull(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isFull])

  if (!inApp) return null

  const btn =
    'flex h-8 w-11 items-center justify-center text-muted transition hover:bg-hover hover:text-ink focus:outline-none'

  const toggleFull = () => {
    call('toggle_fullscreen')
    setIsFull((v) => !v)
  }

  return (
    <div className="flex h-8 shrink-0 items-stretch border-b border-line bg-ground-2 select-none">
      <div className="pywebview-drag-region flex-1" />
      <button
        className={btn}
        onClick={toggleFull}
        aria-label={isFull ? 'Exit full screen' : 'Full screen'}
        title={isFull ? 'Exit full screen' : 'Full screen'}
      >
        {isFull ? (
          <ExitFullscreenIcon width={15} height={15} />
        ) : (
          <FullscreenIcon width={15} height={15} />
        )}
      </button>
      <button className={btn} onClick={() => call('minimize')} aria-label="Minimize" title="Minimize">
        <MinimizeIcon width={15} height={15} />
      </button>
      <button className={btn} onClick={() => call('close')} aria-label="Close" title="Close">
        <CloseIcon width={15} height={15} />
      </button>
    </div>
  )
}
