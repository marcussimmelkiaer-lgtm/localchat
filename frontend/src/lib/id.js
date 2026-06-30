// Small id helper. Prefers crypto.randomUUID (available in WebView2 / modern
// browsers over a secure or localhost origin), with a cheap fallback.
export function newId() {
  try {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID()
    }
  } catch {
    /* ignore */
  }
  return 'id-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10)
}
