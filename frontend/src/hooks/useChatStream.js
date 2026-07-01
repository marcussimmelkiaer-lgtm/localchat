import { useCallback, useEffect, useRef, useState } from 'react'
import { sendMessage } from '../api/llmClient'
import { apiStopGeneration } from '../api/conversations'
import { newId } from '../lib/id'

// Drives a single in-flight generation: appends optimistic messages, streams
// tokens (batched per animation frame so we never render once per token), and
// handles stop/regenerate. Reads the latest conversations controller via a ref
// to keep its callbacks stable.

// Read a File into bare base64 (strips the "data:<mime>;base64," prefix).
function readFileBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = String(reader.result || '')
      const comma = result.indexOf(',')
      resolve(comma === -1 ? result : result.slice(comma + 1))
    }
    reader.onerror = () => reject(reader.error || new Error('file read failed'))
    reader.readAsDataURL(file)
  })
}

export function useChatStream(convo) {
  const [isStreaming, setIsStreaming] = useState(false)

  const convoRef = useRef(convo)
  convoRef.current = convo

  const controllerRef = useRef(null)
  const streamConvRef = useRef(null)
  const streamMsgRef = useRef(null)

  const bufferRef = useRef('')
  const rafRef = useRef(0)

  const flush = useCallback(() => {
    rafRef.current = 0
    const chunk = bufferRef.current
    if (!chunk) return
    bufferRef.current = ''
    const convId = streamConvRef.current
    const msgId = streamMsgRef.current
    if (convId && msgId) {
      convoRef.current.updateMessage(convId, msgId, (m) => ({ content: m.content + chunk }))
    }
  }, [])

  const scheduleFlush = useCallback(() => {
    if (rafRef.current) return
    rafRef.current = requestAnimationFrame(flush)
  }, [flush])

  const finalizeFlush = useCallback(() => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = 0
    }
    flush()
  }, [flush])

  const endStream = useCallback(() => {
    controllerRef.current = null
    streamConvRef.current = null
    streamMsgRef.current = null
    setIsStreaming(false)
  }, [])

  const run = useCallback(
    async ({ convId, content, regenerate, userId, assistantId, priorMessages, attachments }) => {
      const controller = new AbortController()
      controllerRef.current = controller
      streamConvRef.current = convId
      streamMsgRef.current = assistantId
      bufferRef.current = ''
      setIsStreaming(true)

      await sendMessage(
        {
          conversationId: convId,
          content,
          messages: priorMessages,
          regenerate,
          userMessageId: userId,
          assistantMessageId: assistantId,
          attachments,
        },
        {
          signal: controller.signal,
          onToken: (t) => {
            bufferRef.current += t
            scheduleFlush()
          },
          onStats: (stats) => {
            convoRef.current.updateMessage(convId, assistantId, { stats })
          },
          onDone: ({ status }) => {
            finalizeFlush()
            convoRef.current.updateMessage(convId, assistantId, {
              status: status === 'stopped' ? 'stopped' : 'done',
            })
            convoRef.current.touchConversation(convId)
            endStream()
          },
          onError: (message) => {
            finalizeFlush()
            convoRef.current.updateMessage(convId, assistantId, { status: 'error', error: message })
            endStream()
          },
        }
      )
    },
    [scheduleFlush, finalizeFlush, endStream]
  )

  const send = useCallback(
    async (text, files) => {
      const content = (text || '').trim()
      const fileList = files ? Array.from(files) : []
      if ((!content && fileList.length === 0) || controllerRef.current) return
      const c = convoRef.current
      let convId = c.activeId
      if (!convId) convId = (await c.createConversation()).id

      const priorMessages = c.getMessages(convId)
      // Read files to base64 for the wire; keep light metadata for the bubble chip.
      const attachments = await Promise.all(
        fileList.map(async (f) => ({
          name: f.name,
          mime: f.type || '',
          data_b64: await readFileBase64(f),
        }))
      )
      const attachmentMeta = fileList.map((f) => {
        const isImage = (f.type || '').startsWith('image/')
        return {
          name: f.name,
          mime: f.type || '',
          size: f.size,
          is_image: isImage,
          // Local preview so the optimistic bubble shows the image instantly,
          // before the row is persisted and the served endpoint is reachable.
          previewUrl: isImage ? URL.createObjectURL(f) : undefined,
        }
      })
      c.titleConversationIfEmpty(convId, content || fileList[0]?.name || '')

      const userMsg = {
        id: newId(),
        role: 'user',
        content,
        status: 'done',
        stats: null,
        error: null,
        attachments: attachmentMeta,
      }
      const assistantId = newId()
      const assistantMsg = {
        id: assistantId,
        role: 'assistant',
        content: '',
        status: 'streaming',
        stats: null,
        error: null,
      }
      c.appendMessage(convId, userMsg)
      c.appendMessage(convId, assistantMsg)
      c.touchConversation(convId)

      await run({ convId, content, regenerate: false, userId: userMsg.id, assistantId, priorMessages, attachments })
    },
    [run]
  )

  const regenerate = useCallback(async () => {
    if (controllerRef.current) return
    const c = convoRef.current
    const convId = c.activeId
    if (!convId) return
    const msgs = c.getMessages(convId)
    let i = msgs.length - 1
    while (i >= 0 && msgs[i].role !== 'assistant') i--
    if (i < 0) return
    const assistantId = msgs[i].id
    c.updateMessage(convId, assistantId, { content: '', status: 'streaming', stats: null, error: null })
    await run({ convId, content: '', regenerate: true, assistantId, priorMessages: msgs })
  }, [run])

  const stop = useCallback(() => {
    const convId = streamConvRef.current
    controllerRef.current?.abort()
    if (convId) apiStopGeneration(convId)
  }, [])

  useEffect(() => {
    return () => controllerRef.current?.abort()
  }, [])

  return { isStreaming, send, regenerate, stop }
}
