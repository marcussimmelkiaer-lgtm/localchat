// Small, muted tokens/second readout shown under a finished assistant message.
export default function TokensPerSec({ stats, stopped }) {
  if (!stats || !stats.tokensPerSecond) return null
  const tps = stats.tokensPerSecond
  const rounded = tps >= 100 ? Math.round(tps) : tps.toFixed(1)
  return (
    <div className="mt-1.5 select-none text-[12px] text-muted">
      {rounded} tok/s
      {stats.tokens ? ` · ${stats.tokens} tokens` : ''}
      {stopped ? ' · stopped' : ''}
    </div>
  )
}
