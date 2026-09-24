import Composer from './Composer'
import EmptyState from './EmptyState'
import MessageList from './MessageList'
import { SidebarIcon } from './icons'

function statusText({ serverDown, modelError, modelReady, downloadPct }) {
  if (serverDown) return 'Cannot reach the local server'
  if (modelError) return modelError
  if (downloadPct != null) return `Downloading model… ${downloadPct}%`
  if (!modelReady) return 'Preparing model…'
  return null
}

export default function ChatPane({
  messages,
  activeId,
  isStreaming,
  onSend,
  onStop,
  onRegenerate,
  modelReady,
  modelError,
  downloadPct,
  serverDown,
  sidebarCollapsed,
  onExpandSidebar,
}) {
  const isEmpty = messages.length === 0
  const blocked = !modelReady
  const status = statusText({ serverDown, modelError, modelReady, downloadPct })
  const placeholder = serverDown
    ? 'Server unavailable'
    : modelError
      ? 'Model unavailable'
      : downloadPct != null
        ? 'Downloading model (first launch only)…'
        : !modelReady
          ? 'Preparing model…'
          : 'Message…'

  return (
    <div className="relative flex h-full min-w-0 flex-1 flex-col bg-ground">
      <div className="flex h-12 shrink-0 items-center gap-2 px-3">
        {sidebarCollapsed && (
          <button
            onClick={onExpandSidebar}
            className="focus-ring rounded-control p-2 text-muted transition hover:bg-hover hover:text-ink"
            aria-label="Show sidebar"
            title="Show sidebar"
          >
            <SidebarIcon />
          </button>
        )}
        <div className="flex-1" />
        {status && (
          <span className="flex select-none items-center gap-2 rounded-full border border-line px-2.5 py-1 text-[11px] text-muted">
            {!modelReady && !modelError && !serverDown && (
              <span className="h-1.5 w-1.5 animate-dot-pulse rounded-full bg-muted" />
            )}
            {status}
          </span>
        )}
      </div>

      {(modelError || serverDown) && (
        <div className="mx-auto mb-1 w-full max-w-content px-4">
          <div className="rounded-control border border-line bg-bubble px-3 py-2 text-[12.5px] text-muted">
            {serverDown
              ? 'The local backend isn’t reachable. Make sure the app server is running.'
              : `Model unavailable — ${modelError}`}
          </div>
        </div>
      )}

      {isEmpty ? (
        <EmptyState
          onSend={onSend}
          onStop={onStop}
          isStreaming={isStreaming}
          disabled={blocked}
          placeholder={placeholder}
        />
      ) : (
        <>
          <MessageList messages={messages} activeId={activeId} onRegenerate={onRegenerate} />
          <div className="shrink-0 px-4 pb-4 pt-1">
            <div className="mx-auto max-w-content">
              <Composer
                onSend={onSend}
                onStop={onStop}
                isStreaming={isStreaming}
                disabled={blocked}
                placeholder={placeholder}
                autoFocus
              />
              <div className="mt-2 select-none text-center text-[11px] text-muted">
                Responses are generated locally on your machine.
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
