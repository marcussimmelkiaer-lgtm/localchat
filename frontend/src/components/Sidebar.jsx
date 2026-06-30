import ConversationItem from './ConversationItem'
import { PlusIcon, SidebarIcon } from './icons'
import logoUrl from '../assets/logo-nobodywho.png'

export default function Sidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onRename,
  onDelete,
  onCollapse,
}) {
  return (
    <div className="flex h-full w-[260px] shrink-0 flex-col border-r border-line bg-ground-2">
      <div className="flex items-center px-3 pb-1 pt-3.5">
        <img src={logoUrl} alt="NobodyWho" className="h-[18px] w-auto opacity-90" />
      </div>
      <div className="flex items-center gap-2 p-2">
        <button
          onClick={onNew}
          className="focus-ring flex flex-1 items-center gap-2 rounded-control border border-line bg-ground/40 px-3 py-2 text-[13px] font-medium text-ink transition hover:bg-hover"
        >
          <PlusIcon width={16} height={16} /> New chat
        </button>
        <button
          onClick={onCollapse}
          className="focus-ring rounded-control p-2 text-muted transition hover:bg-hover hover:text-ink"
          aria-label="Collapse sidebar"
          title="Collapse sidebar"
        >
          <SidebarIcon />
        </button>
      </div>
      <div className="scroll-thin flex-1 overflow-y-auto px-2 pb-2">
        {conversations.length === 0 ? (
          <div className="px-2 py-3 text-[12px] text-muted">No conversations yet</div>
        ) : (
          <div className="flex flex-col gap-0.5">
            {conversations.map((c) => (
              <ConversationItem
                key={c.id}
                conv={c}
                active={c.id === activeId}
                onSelect={onSelect}
                onRename={onRename}
                onDelete={onDelete}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
