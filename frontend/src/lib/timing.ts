// Pure timing helpers (kept separate from React/DOM code so they are easy to test).

export const DEFAULT_CHUNK_MS = 10_000;
export const MIN_CHUNK_MS = 1_000;
export const NUM_CHUNKS = 6;

// Chunk length for the caller. Defaults to the real 10 s; `?chunkMs=2000` shortens it
// so a demo recording does not have to wait a full minute. Out-of-range or non-numeric
// values fall back to / clamp toward sane limits.
export function parseChunkMs(search: string): number {
  const raw = new URLSearchParams(search).get("chunkMs");
  if (raw === null || raw.trim() === "") return DEFAULT_CHUNK_MS;
  const value = Number(raw);
  if (!Number.isFinite(value)) return DEFAULT_CHUNK_MS;
  return Math.min(DEFAULT_CHUNK_MS, Math.max(MIN_CHUNK_MS, Math.round(value)));
}

// Reconnect delay for the dashboard: 1s, 2s, 4s, 8s, then capped at 10s.
export function nextBackoffMs(attempt: number): number {
  const safe = Math.max(0, Math.floor(attempt));
  return Math.min(10_000, 1_000 * 2 ** Math.min(safe, 10));
}

// Whole seconds left in a capture, never negative.
export function secondsRemaining(totalMs: number, elapsedMs: number): number {
  return Math.max(0, Math.ceil((totalMs - elapsedMs) / 1000));
}
