import { useCallback, useEffect, useRef, useState } from 'react'
import { newId } from '../lib/id'
import {
  apiListConversations,
  apiCreateConversation,
  apiGetConversation,
  apiRenameConversation,
  apiDeleteConversation,
} from '../api/conversations'

// Owns conversations, per-conversation messages, the active id, and persistence.
// Talks to the backend REST API when reachable; otherwise runs purely in memory
// so the UI works standalone. Mutators are stable (useCallback) and read the
// latest state through refs to avoid stale closures during streaming.

const nowIso = () => new Date().toISOString()

const sortConvs = (list) =>
  [...list].sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : a.updatedAt > b.updatedAt ? -1 : 0))

function normConv(c) {
  return {
    id: c.id,
    title: c.title || '',
    createdAt: c.created_at || c.createdAt || nowIso(),
    updatedAt: c.updated_at || c.updatedAt || c.created_at || nowIso(),
  }
}

function normMsg(m) {
  const s = m.stats
  return {
    id: m.id || newId(),
    role: m.role,
    content: m.content ?? '',
    status: m.status || 'done',
    stats: s
      ? {
          tokens: s.tokens ?? 0,
          seconds: s.seconds ?? 0,
          tokensPerSecond: s.tokens_per_second ?? s.tokensPerSecond ?? 0,
          ttftMs: s.ttft_ms ?? s.ttftMs ?? 0,
        }
      : null,
    error: m.error || null,
    attachments: Array.isArray(m.attachments) ? m.attachments : [],
  }
}

function deriveTitle(content) {
  const first = (content || '').trim().split('\n')[0].replace(/\s+/g, ' ')
  if (!first) return 'New chat'
  return first.length > 42 ? first.slice(0, 41) + '…' : first
}

export function useConversations() {
  const [conversations, setConversations] = useState([])
  const [messagesByConv, setMessagesByConv] = useState({})
  const [activeId, setActiveId] = useState(null)
  const [backendAvailable, setBackendAvailable] = useState(false)
  const [ready, setReady] = useState(false)

  const convsRef = useRef([])
  const activeRef = useRef(null)
  const msgsRef = useRef({})
  const hydrated = useRef(new Set()) // conv ids whose messages are in state
  const backendRef = useRef(false)

  useEffect(() => {
    convsRef.current = conversations
  }, [conversations])
  useEffect(() => {
    activeRef.current = activeId
  }, [activeId])
  useEffect(() => {
    msgsRef.current = messagesByConv
  }, [messagesByConv])

  // Initial load from backend (if any).
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const list = await apiListConversations()
      if (cancelled) return
      if (Array.isArray(list)) {
        backendRef.current = true
        setBackendAvailable(true)
        const conv = sortConvs(list.map(normConv))
        setConversations(conv)
        setActiveId(conv.length ? conv[0].id : null)
      }
      setReady(true)
    })()
    return () => {
      cancelled = true
    }
  }, [])

  // Lazy-load messages for the active conversation from the backend.
  useEffect(() => {
    if (!activeId || !backendRef.current || hydrated.current.has(activeId)) return
    let cancelled = false
    ;(async () => {
      const data = await apiGetConversation(activeId)
      if (cancelled) return
      hydrated.current.add(activeId)
      const msgs = Array.isArray(data?.messages) ? data.messages.map(normMsg) : []
      setMessagesByConv((prev) => (prev[activeId] ? prev : { ...prev, [activeId]: msgs }))
    })()
    return () => {
      cancelled = true
    }
  }, [activeId])

  // --- message mutators ---
  const appendMessage = useCallback((convId, msg) => {
    hydrated.current.add(convId)
    setMessagesByConv((prev) => ({ ...prev, [convId]: [...(prev[convId] || []), msg] }))
  }, [])

  const updateMessage = useCallback((convId, msgId, patch) => {
    setMessagesByConv((prev) => {
      const arr = prev[convId]
      if (!arr) return prev
      return {
        ...prev,
        [convId]: arr.map((m) =>
          m.id === msgId ? { ...m, ...(typeof patch === 'function' ? patch(m) : patch) } : m
        ),
      }
    })
  }, [])

  const removeMessage = useCallback((convId, msgId) => {
    setMessagesByConv((prev) => {
      const arr = prev[convId]
      if (!arr) return prev
      return { ...prev, [convId]: arr.filter((m) => m.id !== msgId) }
    })
  }, [])

  const getMessages = useCallback((convId) => msgsRef.current[convId] || [], [])

  // --- conversation mutators ---
  const createConversation = useCallback(async () => {
    const created = await apiCreateConversation(null)
    const conv = created
      ? normConv(created)
      : { id: newId(), title: '', createdAt: nowIso(), updatedAt: nowIso() }
    hydrated.current.add(conv.id)
    setConversations((prev) => sortConvs([conv, ...prev.filter((c) => c.id !== conv.id)]))
    setMessagesByConv((prev) => ({ ...prev, [conv.id]: prev[conv.id] || [] }))
    setActiveId(conv.id)
    return conv
  }, [])

  const renameConversation = useCallback((id, title) => {
    setConversations((prev) => sortConvs(prev.map((c) => (c.id === id ? { ...c, title } : c))))
    apiRenameConversation(id, title)
  }, [])

  const deleteConversation = useCallback((id) => {
    const remaining = sortConvs(convsRef.current.filter((c) => c.id !== id))
    setConversations(remaining)
    setMessagesByConv((prev) => {
      const next = { ...prev }
      delete next[id]
      return next
    })
    hydrated.current.delete(id)
    setActiveId((cur) => (cur === id ? remaining[0]?.id ?? null : cur))
    apiDeleteConversation(id)
  }, [])

  // Bump updatedAt (reorders the sidebar to most-recent-first).
  const touchConversation = useCallback((id) => {
    setConversations((prev) =>
      sortConvs(prev.map((c) => (c.id === id ? { ...c, updatedAt: nowIso() } : c)))
    )
  }, [])

  // Set a title derived from the first user message, only if still untitled.
  const titleConversationIfEmpty = useCallback((id, content) => {
    const conv = convsRef.current.find((c) => c.id === id)
    if (!conv || conv.title) return
    const title = deriveTitle(content)
    setConversations((prev) => prev.map((c) => (c.id === id ? { ...c, title } : c)))
    apiRenameConversation(id, title)
  }, [])

  const activeMessages = activeId ? messagesByConv[activeId] || [] : []

  return {
    conversations,
    activeId,
    activeMessages,
    backendAvailable,
    ready,
    setActiveId,
    createConversation,
    renameConversation,
    deleteConversation,
    touchConversation,
    titleConversationIfEmpty,
    appendMessage,
    updateMessage,
    removeMessage,
    getMessages,
  }
}
