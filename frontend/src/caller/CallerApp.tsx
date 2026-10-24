import { useEffect, useMemo, useRef, useState } from "react";
import { createReport, fetchScenarios, openCaptureStream } from "../lib/api";
import {
  getLocation,
  MicDeniedError,
  MicUnavailableError,
  recordInChunks,
  requestMic,
  scheduleChunks,
} from "../lib/capture";
import { loadSoundDetector, type SoundDetector } from "../lib/sounds";
import { speechSupported, startSpeech, type SpeechSession } from "../lib/speech";
import { NUM_CHUNKS, parseChunkMs, secondsRemaining } from "../lib/timing";
import {
  type RouteDecisionView,
  type ScenarioInfo,
  type StatusKey,
  STATUS_KEYS,
} from "../lib/types";
import { HeardPanel, type HeardChunk } from "./HeardPanel";
import { RouteSummary } from "./RouteSummary";

const ACTIVE: StatusKey[] = ["LISTENING", "PROVISIONAL_ROUTE", "REFINED_ROUTE"];

type SoundStatus = "loading" | "ready" | "unavailable";

export function CallerApp(): JSX.Element {
  const chunkMs = useMemo(() => parseChunkMs(window.location.search), []);
  // `?demo=1` swaps the microphone for a scripted scenario (offline demos, recordings).
  const demo = useMemo(() => new URLSearchParams(window.location.search).get("demo") === "1", []);
  const totalMs = chunkMs * NUM_CHUNKS;

  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [scenario, setScenario] = useState<string>("");
  const [status, setStatus] = useState<StatusKey>("IDLE");
  const [secondsLeft, setSecondsLeft] = useState<number>(0);
  const [decision, setDecision] = useState<RouteDecisionView | null>(null);
  const [heard, setHeard] = useState<HeardChunk[]>([]);
  const [soundStatus, setSoundStatus] = useState<SoundStatus>("loading");
  const [error, setError] = useState<string | null>(null);
  const cancelRef = useRef<(() => void) | null>(null);
  const detectorRef = useRef<Promise<SoundDetector | null> | null>(null);
  const speechOk = useMemo(() => speechSupported(), []);

  useEffect(() => {
    if (demo) {
      fetchScenarios()
        .then((s) => {
          setScenarios(s);
          if (s.length > 0) setScenario(s[0].id);
        })
        .catch(() => setScenarios([]));
    } else {
      // Load the sound model while the caller is still reading the page, so the first
      // chunk is not delayed by a download.
      detectorRef.current = loadSoundDetector()
        .then((detector) => {
          setSoundStatus("ready");
          return detector;
        })
        .catch(() => {
          setSoundStatus("unavailable");
          return null;
        });
    }
    // Leaving the page must stop the recorder, release the mic, and close the socket.
    return () => cancelRef.current?.();
  }, [demo]);

  function fail(key: StatusKey, message: string = STATUS_KEYS[key]): void {
    setStatus(key);
    setError(message);
  }

  async function handleHelp(): Promise<void> {
    setError(null);
    setDecision(null);
    setHeard([]);

    // 1. Microphone first (not needed in demo mode), so a refusal is explained.
    let stream: MediaStream | null = null;
    if (!demo) {
      try {
        stream = await requestMic();
      } catch (e) {
        if (e instanceof MicUnavailableError) fail("MIC_UNAVAILABLE");
        else if (e instanceof MicDeniedError) fail("MIC_DENIED");
        else fail("ERROR");
        return;
      }
    }

    setStatus("LISTENING");
    setSecondsLeft(secondsRemaining(totalMs, 0));

    // 2. Chunks queue up until the socket is ready, so a slow location fix never delays
    //    listening.
    const outbox: string[] = [];
    let socket: WebSocket | null = null;
    let finished = false;
    let cancelled = false;

    const flush = (): void => {
      while (socket && socket.readyState === WebSocket.OPEN && outbox.length > 0) {
        socket.send(outbox.shift() as string);
      }
    };
    const enqueue = (message: object): void => {
      outbox.push(JSON.stringify(message));
      flush();
    };

    // Chunks are processed one at a time so "end" can never overtake the last chunk.
    let chain: Promise<void> = Promise.resolve();
    const onDone = (): void => {
      chain = chain.then(() => enqueue({ type: "end" }));
    };

    let stopSource: () => void;
    let speech: SpeechSession | null = null;

    if (demo) {
      // Scripted scenario: the server supplies the signals; we only pace the chunks.
      stopSource = scheduleChunks(
        chunkMs,
        NUM_CHUNKS,
        (index) => {
          chain = chain.then(() => enqueue({ type: "chunk", chunk_index: index }));
        },
        onDone,
      );
    } else {
      // Real capture: speech-to-text and sound classification both run on this device.
      speech = speechOk ? startSpeech() : null;
      stopSource = recordInChunks(
        stream as MediaStream,
        chunkMs,
        NUM_CHUNKS,
        (blob, index) => {
          // Read the words now (the chunk boundary), analyze the sound afterwards.
          const text = speech ? speech.take() : null;
          chain = chain.then(async () => {
            let events: HeardChunk["events"] = null;
            try {
              const detector = await detectorRef.current;
              if (detector) events = await detector.detect(blob);
            } catch {
              events = null; // sound detection failed for this chunk; say so, carry on
            }
            setHeard((prev) => [...prev, { index, text, events }]);
            enqueue({ type: "chunk", chunk_index: index, transcript: text, events });
          });
        },
        onDone,
      );
    }

    const startedAt = Date.now();
    const ticker = setInterval(() => {
      setSecondsLeft(secondsRemaining(totalMs, Date.now() - startedAt));
    }, 500);

    const cancel = (): void => {
      cancelled = true;
      clearInterval(ticker);
      stopSource();
      speech?.stop();
      socket?.close();
    };
    cancelRef.current = cancel;

    const abort = (key: StatusKey, message?: string): void => {
      if (finished || cancelled) return;
      finished = true;
      cancel();
      fail(key, message);
    };

    // 3. Location and report creation run alongside listening.
    try {
      const loc = await getLocation();
      const { id } = await createReport({
        scenario: demo ? scenario || undefined : undefined,
        lat: loc.lat ?? undefined,
        lon: loc.lon ?? undefined,
        accuracy_m: loc.accuracy_m ?? undefined,
      });
      if (cancelled) return;

      const ws = openCaptureStream(id);
      socket = ws;
      ws.onopen = flush;
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.type === "route") {
          setDecision(msg.decision);
          setStatus(msg.decision.status === "refined" ? "REFINED_ROUTE" : "PROVISIONAL_ROUTE");
        } else if (msg.type === "closed") {
          finished = true;
          clearInterval(ticker);
          speech?.stop();
          setDecision(msg.decision);
          setSecondsLeft(0);
          setStatus("SENT_TO_DISPATCH");
          ws.close();
        } else if (msg.type === "error") {
          abort("ERROR", String(msg.detail));
        }
      };
      ws.onerror = () => abort("CONNECTION_LOST");
      ws.onclose = () => abort("CONNECTION_LOST");
    } catch (e) {
      abort("ERROR", e instanceof Error ? e.message : STATUS_KEYS.ERROR);
    }
  }

  const active = ACTIVE.includes(status);
  const capabilityNotes: string[] = [];
  if (!demo) {
    if (!speechOk) capabilityNotes.push("This browser can’t transcribe speech, so only sounds will be used.");
    if (soundStatus === "unavailable")
      capabilityNotes.push("Sound detection couldn’t load, so only speech will be used.");
  }

  return (
    <main className="caller">
      <p className="demo-banner" role="note">
        Demo only. No real emergency service is contacted. A human confirms every dispatch.
      </p>

      <h1>Help Router</h1>

      {demo && (
        <>
          <label className="scenario">
            Scripted scenario (demo mode)
            <select
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
              disabled={active}
            >
              {scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <p className="speed-note">
            Demo mode plays a scripted scenario and does not use your microphone.
          </p>
        </>
      )}

      {chunkMs !== 10_000 && (
        <p className="speed-note">Fast mode: {chunkMs / 1000}s chunks instead of 10s.</p>
      )}

      <button
        className="help-button"
        onClick={handleHelp}
        disabled={active}
        aria-label="Press for help. Listens for 60 seconds and shares your location."
      >
        {active ? "Listening…" : "Help"}
      </button>

      <p className="status" role="status" aria-live="assertive">
        {error ? "" : STATUS_KEYS[status]}
        {!error && active && secondsLeft > 0 ? ` — ${secondsLeft}s left` : ""}
      </p>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {capabilityNotes.map((note) => (
        <p key={note} className="speed-note" role="status">
          {note}
        </p>
      ))}

      {!demo && status === "IDLE" && (
        <p className="speed-note">
          Your browser turns speech into text (Chrome uses Google’s speech service) and sounds
          are analysed on this device. We receive only the text and sound labels, not audio.
        </p>
      )}

      <HeardPanel chunks={heard} />
      {decision && <RouteSummary decision={decision} />}
    </main>
  );
}
