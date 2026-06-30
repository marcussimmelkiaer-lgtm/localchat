import Composer from './Composer'
import logoUrl from '../assets/logo-nobodywho.png'

// Cold-start: a quiet centered greeting with the composer mid-screen. Once the
// conversation has messages, ChatPane swaps this for the message list + a
// bottom-docked composer.
export default function EmptyState({ onSend, onStop, isStreaming, disabled, placeholder }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4 pb-16">
      <div className="w-full max-w-content">
        <img
          src={logoUrl}
          alt="NobodyWho"
          className="mx-auto mb-5 h-7 w-auto opacity-90"
        />
        <h1 className="mb-7 text-center text-[28px] font-semibold tracking-tight text-ink">
          What can I help with?
        </h1>
        <Composer
          onSend={onSend}
          onStop={onStop}
          isStreaming={isStreaming}
          disabled={disabled}
          placeholder={placeholder}
          autoFocus
        />
      </div>
    </div>
  )
}
