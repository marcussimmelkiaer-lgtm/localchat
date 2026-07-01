// REST client for the model manager: list catalog, poll download/switch status,
// and trigger download / switch / delete. List + status degrade to null when the
// backend is unreachable (like api/conversations); the action calls return
// { ok, error } so the UI can surface a 409 message ("Stop generation first").

async function get(url) {
  try {
    const res = await fetch(url, { method: 'GET' })
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

async function action(method, url, body) {
  try {
    const res = await fetch(url, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    })
    if (res.ok) {
      const ct = res.headers.get('content-type') || ''
      const data = ct.includes('application/json') ? await res.json() : {}
      return { ok: true, ...data }
    }
    let detail = `Request failed (${res.status})`
    try {
      const j = await res.json()
      if (j?.detail) detail = j.detail
    } catch {
      /* keep default */
    }
    return { ok: false, error: detail }
  } catch {
    return { ok: false, error: 'Could not reach the local server.' }
  }
}

export const apiListModels = () => get('/api/models')
export const apiModelStatus = () => get('/api/models/status')
export const apiDownloadModel = (spec, thenSwitch = true, extraSpecs = []) =>
  action('POST', '/api/models/download', { spec, then_switch: thenSwitch, extra_specs: extraSpecs })
export const apiSwitchModel = (path) => action('POST', '/api/models/switch', { path })
export const apiDeleteModel = (path) => action('DELETE', '/api/models', { path })
