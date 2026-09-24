import { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar'
import ChatPane from './components/ChatPane'
import TitleBar from './components/TitleBar'
import ModelPicker from './components/ModelPicker'
import { useConversations } from './hooks/useConversations'
import { useChatStream } from './hooks/useChatStream'
import { useModelManager } from './hooks/useModelManager'
import { getHealth, refreshHealth, triggerWarmup } from './api/health'

export default function App() {
  const convo = useConversations()
  const chat = useChatStream(convo)
  const models = useModelManager()
  const [collapsed, setCollapsed] = useState(false)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [health, setHealth] = useState(null)

  useEffect(() => {
    let alive = true
    getHealth().then((h) => alive && setHealth(h))
    return () => {
      alive = false
    }
  }, [])

  // Once the conversation list has rendered, ask the backend to load the model
  // in the background and poll until it's ready. Loading holds the GIL for ~3s
  // on the backend; deferring it to here (after the UI is up) keeps the initial
  // render snappy — the UI is a separate WebView2 process, so it stays smooth
  // while the backend loads. The composer is disabled (with a loading hint)
  // until the model is ready, so the first message is instant.
  useEffect(() => {
    if (!convo.ready) return
    let alive = true
    let timer
    const tick = async (kick) => {
      if (kick) triggerWarmup()
      const h = await refreshHealth()
      if (!alive) return
      setHealth(h)
      if (!h.available || h.modelLoaded || h.modelError) return
      timer = setTimeout(() => tick(false), 600)
    }
    tick(true)
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [convo.ready])

  // A model switch/download clears the backend's model_loaded flag while the new
  // weights load, so re-poll /healthz while a model task is active (and once more
  // after it settles) to flip the composer's "Preparing model…" gate correctly.
  const taskStatus = models.task?.status
  useEffect(() => {
    if (taskStatus !== 'loading' && taskStatus !== 'downloading' && taskStatus !== 'ready') return
    let alive = true
    let timer
    const tick = async () => {
      const h = await refreshHealth()
      if (!alive) return
      setHealth(h)
      if (!h.available || h.modelLoaded || h.modelError) return
      timer = setTimeout(tick, 600)
    }
    tick()
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [taskStatus])

  const serverDown = health ? !health.available : false
  const modelError = health?.modelError || null
  const modelReady = !serverDown && !!health?.modelLoaded
  // A packaged build downloads its model on first launch; show that progress
  // instead of a bare "Preparing model…".
  const task = health?.modelTask
  const downloadPct =
    !modelReady && task?.status === 'downloading' ? Math.round((task.fraction || 0) * 100) : null

  return (
    <div className="flex h-full w-full flex-col overflow-hidden bg-ground-2 text-ink">
      <TitleBar />
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {!collapsed && (
          <Sidebar
            conversations={convo.conversations}
            activeId={convo.activeId}
            onSelect={convo.setActiveId}
            onNew={() => convo.createConversation()}
            onRename={convo.renameConversation}
            onDelete={convo.deleteConversation}
            onCollapse={() => setCollapsed(true)}
            activeModel={models.data?.active}
            modelBusy={models.busy}
            onOpenModels={() => setPickerOpen(true)}
          />
        )}
        <ChatPane
          messages={convo.activeMessages}
          activeId={convo.activeId}
          isStreaming={chat.isStreaming}
          onSend={chat.send}
          onStop={chat.stop}
          onRegenerate={chat.regenerate}
          modelReady={modelReady}
          modelError={modelError}
          downloadPct={downloadPct}
          serverDown={serverDown}
          sidebarCollapsed={collapsed}
          onExpandSidebar={() => setCollapsed(false)}
        />
      </div>
      {pickerOpen && <ModelPicker mgr={models} onClose={() => setPickerOpen(false)} />}
    </div>
  )
}
