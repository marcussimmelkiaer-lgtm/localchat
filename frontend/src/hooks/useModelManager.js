import { useCallback, useEffect, useRef, useState } from 'react'
import {
  apiDeleteModel,
  apiDownloadModel,
  apiListModels,
  apiModelStatus,
  apiSwitchModel,
} from '../api/models'

// Owns the model list + the current download/switch task. While a task is
// running (status downloading|loading) it polls /api/models/status every ~600ms
// — the same alive-flag + setTimeout pattern App.jsx uses for health. On task
// completion it refreshes the list. A switch clears the backend's model_loaded
// flag, so App.jsx's existing health poll disables the composer for free; this
// hook only owns the picker's own state.
const POLL_MS = 600
const TASK_ACTIVE = (s) => s === 'downloading' || s === 'loading'

export function useModelManager() {
  const [data, setData] = useState(null) // { active, catalog, cached }
  const [task, setTask] = useState({ status: 'idle', fraction: 0, error: null })
  const [actionError, setActionError] = useState(null)
  const pollRef = useRef(null)
  const aliveRef = useRef(true)

  const refresh = useCallback(async () => {
    const d = await apiListModels()
    if (d && aliveRef.current) setData(d)
    return d
  }, [])

  useEffect(() => {
    aliveRef.current = true
    refresh()
    return () => {
      aliveRef.current = false
      clearTimeout(pollRef.current)
    }
  }, [refresh])

  // Poll the task status while one is active; refresh the list when it settles.
  const poll = useCallback(async () => {
    const s = await apiModelStatus()
    if (!aliveRef.current || !s) return
    setTask(s)
    if (TASK_ACTIVE(s.status)) {
      pollRef.current = setTimeout(poll, POLL_MS)
    } else {
      refresh() // ready or error — pick up downloaded/active changes
    }
  }, [refresh])

  // Kick off polling without resetting the task — callers set an optimistic task
  // (with `target`) first so the picker can show progress immediately, before the
  // first /status response lands.
  const startPolling = useCallback(() => {
    clearTimeout(pollRef.current)
    pollRef.current = setTimeout(poll, 0)
  }, [poll])

  const download = useCallback(
    async (spec, thenSwitch = true, extraSpecs = []) => {
      setActionError(null)
      const res = await apiDownloadModel(spec, thenSwitch, extraSpecs)
      if (!res.ok) {
        setActionError(res.error)
        return false
      }
      setTask({ status: 'downloading', fraction: 0, error: null, target: spec, action: 'download' })
      startPolling()
      return true
    },
    [startPolling]
  )

  const switchTo = useCallback(
    async (path) => {
      setActionError(null)
      const res = await apiSwitchModel(path)
      if (!res.ok) {
        setActionError(res.error)
        return false
      }
      setTask({ status: 'loading', fraction: 0, error: null, target: path, action: 'switch' })
      startPolling()
      return true
    },
    [startPolling]
  )

  const remove = useCallback(
    async (path) => {
      setActionError(null)
      const res = await apiDeleteModel(path)
      if (!res.ok) {
        setActionError(res.error)
        return false
      }
      if (aliveRef.current) setData(res) // delete returns the fresh list
      return true
    },
    []
  )

  return {
    data,
    task,
    busy: TASK_ACTIVE(task.status),
    actionError,
    clearActionError: () => setActionError(null),
    refresh,
    download,
    switchTo,
    remove,
  }
}
