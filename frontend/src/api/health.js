// Probes the local backend's /healthz to learn whether the model is ready.
// Shape: { available, modelLoaded, modelError, modelTask }

let cached = null
let inflight = null

async function probe() {
  try {
    const res = await fetch('/healthz', { method: 'GET' })
    if (!res.ok) throw new Error('bad status ' + res.status)
    const data = await res.json()
    return {
      available: true,
      modelLoaded: !!data.model_loaded,
      modelError: data.model_error || null,
      modelTask: data.model_task || null,
    }
  } catch {
    return { available: false, modelLoaded: false, modelError: null, modelTask: null }
  }
}

export async function getHealth() {
  if (cached) return cached
  if (!inflight) inflight = probe().then((h) => ((cached = h), (inflight = null), h))
  return inflight
}

export async function refreshHealth() {
  cached = null
  inflight = null
  return getHealth()
}

// Ask the backend to start loading the model in the background (idempotent).
// Returns immediately; readiness is observed via refreshHealth().
export async function triggerWarmup() {
  try {
    await fetch('/api/warmup', { method: 'POST' })
  } catch {
    /* ignore — the health poll will surface any error */
  }
}
