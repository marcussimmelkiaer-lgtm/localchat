import { ChipIcon, ChevronDownIcon } from './icons'

// Sidebar footer row showing the active model; opens the ModelPicker modal.
export default function ModelManagerButton({ active, busy, onOpen }) {
  const name = active?.name ? prettyName(active.name) : 'No model'
  return (
    <button
      onClick={onOpen}
      className="focus-ring flex w-full items-center gap-2 rounded-control border border-line bg-ground/40 px-3 py-2 text-left text-[12.5px] text-ink transition hover:bg-hover"
      title="Manage models"
    >
      <ChipIcon width={15} height={15} className="shrink-0 text-muted" />
      <span className="min-w-0 flex-1 truncate">{name}</span>
      {busy ? (
        <span className="h-1.5 w-1.5 animate-dot-pulse rounded-full bg-muted" />
      ) : (
        <ChevronDownIcon width={14} height={14} className="shrink-0 text-muted" />
      )}
    </button>
  )
}

// "Qwen3-4B-Q4_K_M.gguf" -> "Qwen3-4B-Q4_K_M"
function prettyName(filename) {
  return filename.replace(/\.gguf$/i, '')
}
