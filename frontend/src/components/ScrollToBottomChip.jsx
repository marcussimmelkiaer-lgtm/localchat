import { ChevronDownIcon } from './icons'

// Appears (bottom-center of the chat pane) only when the user has scrolled up
// away from the bottom during/after streaming.
export default function ScrollToBottomChip({ onClick }) {
  return (
    <button
      onClick={onClick}
      className="focus-ring absolute bottom-3 left-1/2 z-10 flex h-9 w-9 -translate-x-1/2 animate-fade-in-fast items-center justify-center rounded-full border border-line bg-ground text-ink shadow-composer transition hover:bg-hover"
      aria-label="Scroll to bottom"
    >
      <ChevronDownIcon width={18} height={18} />
    </button>
  )
}
