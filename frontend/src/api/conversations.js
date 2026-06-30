// REST client for conversation persistence. Each call returns its parsed result
// on success, or null when the backend is unreachable — the caller
// (useConversations) then falls back to purely in-memory state, so the UI runs
// standalone with no server.

async function req(method, url, body) {
  try {
    const res = await fetch(url, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    })
    if (!res.ok) return null
    if (res.status === 204) return true
    const ct = res.headers.get('content-type') || ''
    return ct.includes('application/json') ? await res.json() : true
  } catch {
    return null
  }
}

export const apiListConversations = () => req('GET', '/api/conversations')
export const apiCreateConversation = (title) =>
  req('POST', '/api/conversations', { title: title ?? null })
export const apiGetConversation = (id) => req('GET', `/api/conversations/${id}`)
export const apiRenameConversation = (id, title) =>
  req('PATCH', `/api/conversations/${id}`, { title })
export const apiDeleteConversation = (id) => req('DELETE', `/api/conversations/${id}`)
export const apiStopGeneration = (id) =>
  req('POST', '/api/chat/stop', { conversation_id: id })
