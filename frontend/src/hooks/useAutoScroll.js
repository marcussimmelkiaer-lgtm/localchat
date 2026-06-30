import { useCallback, useEffect, useRef, useState } from 'react'

// Keeps a scroll container pinned to the bottom as content grows, but detaches
// the moment the user scrolls up — exposing isPinned so a "scroll to bottom"
// chip can appear. Programmatic scrolls are flagged so they aren't misread as a
// user scroll-up.
//
// Usage: attach `containerRef` to the scrollable element, whose FIRST child is
// the growing content. Call `pin()` on conversation switch.

const THRESHOLD = 56

export function useAutoScroll(containerRef) {
  const [isPinned, setIsPinned] = useState(true)
  const pinnedRef = useRef(true)
  const programmatic = useRef(false)

  const computePinned = useCallback(() => {
    const el = containerRef.current
    if (!el) return true
    return el.scrollHeight - el.scrollTop - el.clientHeight < THRESHOLD
  }, [containerRef])

  const scrollToBottom = useCallback(
    (behavior = 'auto') => {
      const el = containerRef.current
      if (!el) return
      programmatic.current = true
      el.scrollTo({ top: el.scrollHeight, behavior })
      pinnedRef.current = true
      setIsPinned(true)
      // Clear the flag after the scroll settles (two frames covers smooth start).
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          programmatic.current = false
        })
      )
    },
    [containerRef]
  )

  const pin = useCallback(() => {
    pinnedRef.current = true
    setIsPinned(true)
    scrollToBottom('auto')
  }, [scrollToBottom])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const onScroll = () => {
      if (programmatic.current) return
      const p = computePinned()
      if (p !== pinnedRef.current) {
        pinnedRef.current = p
        setIsPinned(p)
      }
    }
    el.addEventListener('scroll', onScroll, { passive: true })

    // Follow content growth (streaming tokens, new messages) while pinned.
    const ro = new ResizeObserver(() => {
      if (pinnedRef.current) {
        const target = el.scrollHeight
        programmatic.current = true
        el.scrollTop = target
        requestAnimationFrame(() => {
          programmatic.current = false
        })
      }
    })
    if (el.firstElementChild) ro.observe(el.firstElementChild)

    return () => {
      el.removeEventListener('scroll', onScroll)
      ro.disconnect()
    }
  }, [containerRef, computePinned])

  return { isPinned, scrollToBottom, pin }
}
