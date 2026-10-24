import type { AudioEventView } from "../lib/types";

// What the device made of each chunk. null = that signal was unavailable for the chunk.
export interface HeardChunk {
  index: number;
  text: string | null;
  events: AudioEventView[] | null;
}

function describe(chunk: HeardChunk): string {
  const words = chunk.text === null ? "speech unavailable" : chunk.text ? `“${chunk.text}”` : "…";
  const sounds =
    chunk.events === null
      ? "sounds unavailable"
      : chunk.events.length === 0
        ? "no notable sounds"
        : chunk.events
            .map((e) => `${e.kind.replace(/_/g, " ")} ${Math.round(e.confidence * 100)}%`)
            .join(", ");
  return `${words} · ${sounds}`;
}

export function HeardPanel({ chunks }: { chunks: HeardChunk[] }): JSX.Element | null {
  if (chunks.length === 0) return null;
  return (
    <section className="heard" aria-label="What the app heard">
      <h2>What we heard</h2>
      <ol>
        {chunks.map((c) => (
          <li key={c.index}>{describe(c)}</li>
        ))}
      </ol>
    </section>
  );
}
