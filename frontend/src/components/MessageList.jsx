import { useEffect, useRef } from 'react'
import Message from './Message'
import ScrollToBottomChip from './ScrollToBottomChip'
import { useAutoScroll } from '../hooks/useAutoScroll'

export default function MessageList({ messages, activeId, onRegenerate }) {
  const containerRef = useRef(null)
  const { isPinned, scrollToBottom, pin } = useAutoScroll(containerRef)

  // On conversation switch, jump to the bottom and re-pin.
  useEffect(() => {
    pin()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId])

  return (
    <div className="relative min-h-0 flex-1">
      <div ref={containerRef} className="scroll-thin h-full overflow-y-auto">
        <div className="mx-auto flex max-w-content flex-col gap-6 px-4 py-6">
          {messages.map((m, i) => (
            <Message
              key={m.id}
              message={m}
              isLast={i === messages.length - 1}
              onRegenerate={onRegenerate}
            />
          ))}
        </div>
      </div>
      {!isPinned && <ScrollToBottomChip onClick={() => scrollToBottom('smooth')} />}
    </div>
  )
}
