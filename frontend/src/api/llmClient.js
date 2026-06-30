// The single transport seam. The UI calls sendMessage(...) and tokens stream
// from the local NobodyWho backend over SSE (delivered as a POST fetch +
// ReadableStream so we can carry a body and abort cleanly).
//
//   sendMessage(
//     { conversationId, content, regenerate, userMessageId, assistantMessageId },
//     { onToken, onStats, onDone, onError, signal }
//   ) -> Promise<void>
//
// Callbacks:
//   onToken(text)
//   onStats({ tokens, seconds, tokensPerSecond, ttftMs })
//   onDone({ status: 'done' | 'stopped' })
//   onError(message)

export async function sendMessage(payload, handlers) {
  const { conversationId, content, regenerate, userMessageId, assistantMessageId, attachments } = payload
  const { onToken, onStats, onDone, onError, signal } = handlers

  const url = regenerate ? '/api/chat/regenerate' : '/api/chat/stream'
  const body = regenerate
    ? { conversation_id: conversationId, assistant_message_id: assistantMessageId }
    : {
        conversation_id: conversationId,
        content,
        user_message_id: userMessageId,
        assistant_message_id: assistantMessageId,
        attachments: attachments || [],
      }

  let res
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    })
  } catch (err) {
    if (signal?.aborted) return onDone?.({ status: 'stopped' })
    return onError?.(humanizeError(err))
  }

  if (!res.ok || !res.body) {
    let body = null
    try {
      body = await res.json()
    } catch {
      /* ignore */
    }
    return onError?.(formatDetail(body?.detail, res.status))
  }

  await parseSse(res.body, handlers, signal)
}

async function parseSse(stream, { onToken, onStats, onDone, onError }, signal) {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  let terminal = false

  const dispatch = (frame) => {
    const { event } = frame
    let data = null
    if (frame.data) {
      try {
        data = JSON.parse(frame.data)
      } catch {
        data = frame.data
      }
    }
    if (event === 'token') {
      onToken?.(typeof data === 'string' ? data : data?.text ?? '')
    } else if (event === 'stats') {
      onStats?.(normalizeStats(data || {}))
    } else if (event === 'done') {
      terminal = true
      onDone?.({ status: data?.status || 'done' })
    } else if (event === 'error') {
      terminal = true
      onError?.(data?.message || 'Generation error')
    }
  }

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      buf = buf.replace(/\r\n/g, '\n')
      const parts = buf.split('\n\n')
      buf = parts.pop() ?? ''
      for (const part of parts) {
        const frame = parseFrame(part)
        if (frame) dispatch(frame)
      }
    }
  } catch (err) {
    if (signal?.aborted) {
      if (!terminal) onDone?.({ status: 'stopped' })
      return
    }
    if (!terminal) onError?.(humanizeError(err))
    return
  } finally {
    try {
      reader.releaseLock()
    } catch {
      /* ignore */
    }
  }
  if (buf.trim()) {
    const frame = parseFrame(buf)
    if (frame) dispatch(frame)
  }
  if (!terminal) onDone?.({ status: 'done' })
}

function parseFrame(block) {
  let event = 'message'
  const dataLines = []
  for (const line of block.split('\n')) {
    if (!line || line.startsWith(':')) continue // blank or comment (keep-alive)
    const ci = line.indexOf(':')
    const field = ci === -1 ? line : line.slice(0, ci)
    let val = ci === -1 ? '' : line.slice(ci + 1)
    if (val.startsWith(' ')) val = val.slice(1)
    if (field === 'event') event = val
    else if (field === 'data') dataLines.push(val)
  }
  if (dataLines.length === 0 && event === 'message') return null
  return { event, data: dataLines.join('\n') }
}

function normalizeStats(s) {
  return {
    tokens: s.tokens ?? 0,
    seconds: s.seconds ?? 0,
    tokensPerSecond: s.tokens_per_second ?? s.tokensPerSecond ?? 0,
    ttftMs: s.ttft_ms ?? s.ttftMs ?? 0,
  }
}

function humanizeError(err) {
  return err?.message ? String(err.message) : String(err)
}

// FastAPI error `detail` may be a string, an object, or a 422 array of error
// objects. Always reduce it to a readable string — never hand a non-string to
// the UI (rendering an object/array as a React child throws).
function formatDetail(detail, status) {
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail)) {
    const msg = detail.map((d) => d?.msg || JSON.stringify(d)).join('; ')
    if (msg) return msg
  }
  if (detail && typeof detail === 'object') return detail.msg || JSON.stringify(detail)
  return `Server error (${status})`
}
