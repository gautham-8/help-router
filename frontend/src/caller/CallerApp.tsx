import { useEffect, useMemo, useRef, useState } from "react";
import { createReport, fetchScenarios, openCaptureStream } from "../lib/api";
import {
  getLocation,
  MicDeniedError,
  MicUnavailableError,
  recordInChunks,
  type CaptureControl,
  requestMic,
  scheduleChunks,
} from "../lib/capture";
import { loadSoundDetector, type SoundDetector } from "../lib/sounds";
import {
  listenForWakeWord,
  speechSupported,
  startSpeech,
  type SpeechSession,
  type WakeListener,
} from "../lib/speech";
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

// The voice trigger is opt-in (it keeps the browser's speech service listening while the
// page is open), and the choice is remembered so it is already on in an emergency.
const VOICE_TRIGGER_KEY = "helpRouter.voiceTrigger";

function savedVoiceTrigger(): boolean {
  try {
    return window.localStorage.getItem(VOICE_TRIGGER_KEY) === "on";
  } catch {
    return false;
  }
}

function saveVoiceTrigger(on: boolean): void {
  try {
    window.localStorage.setItem(VOICE_TRIGGER_KEY, on ? "on" : "off");
  } catch {
    // storage blocked (private mode); the toggle still works for this visit
  }
}

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
  const finishRef = useRef<(() => void) | null>(null);
  const [stopping, setStopping] = useState<boolean>(false);
  const detectorRef = useRef<Promise<SoundDetector | null> | null>(null);
  const speechOk = useMemo(() => speechSupported(), []);
  const voiceTriggerAvailable = !demo && speechOk;
  const [voiceTrigger, setVoiceTrigger] = useState<boolean>(savedVoiceTrigger);
  const [voiceTriggerError, setVoiceTriggerError] = useState<string | null>(null);
  const wakeRef = useRef<WakeListener | null>(null);
  // The wake listener outlives renders, so it calls the latest handleHelp through a ref.
  const helpRef = useRef<(heard?: string) => Promise<void>>(async () => {});

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

  // Voice trigger: while idle (and after each report finishes), listen for "help".
  const capturing = ACTIVE.includes(status);
  useEffect(() => {
    if (!voiceTriggerAvailable || !voiceTrigger || capturing) return;
    const stopTrigger = (message: string): void => {
      wakeRef.current = null;
      setVoiceTrigger(false);
      setVoiceTriggerError(message);
    };
    const listener = listenForWakeWord(
      (heard) => {
        wakeRef.current = null;
        void helpRef.current(heard);
      },
      () => stopTrigger("Voice trigger stopped: speech recognition isn’t allowed. Press Help instead."),
    );
    if (!listener) {
      stopTrigger("Voice trigger couldn’t start. Press Help instead.");
      return;
    }
    wakeRef.current = listener;
    return () => {
      listener.stop();
      if (wakeRef.current === listener) wakeRef.current = null;
    };
    // `status` (not just `capturing`) so it re-arms after any outcome, including a
    // trigger that failed before capture began (e.g. microphone denied).
  }, [voiceTriggerAvailable, voiceTrigger, status]);

  function toggleVoiceTrigger(): void {
    const next = !voiceTrigger;
    setVoiceTriggerError(null);
    setVoiceTrigger(next);
    saveVoiceTrigger(next);
  }

  function fail(key: StatusKey, message: string = STATUS_KEYS[key]): void {
    setStatus(key);
    setError(message);
  }

  // `heard` is set when the voice trigger started this capture: the words from "help"
  // onward, which go into the first chunk so nothing said with the trigger is lost.
  async function handleHelp(heard?: string): Promise<void> {
    // Release the wake listener first; only one recognizer can run at a time.
    wakeRef.current?.stop();
    wakeRef.current = null;
    let triggerText = heard ?? "";

    setStopping(false);
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

    let source: CaptureControl;
    let speech: SpeechSession | null = null;

    if (demo) {
      // Scripted scenario: the server supplies the signals; we only pace the chunks.
      source = scheduleChunks(
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
      source = recordInChunks(
        stream as MediaStream,
        chunkMs,
        NUM_CHUNKS,
        (blob, index) => {
          // Read the words now (the chunk boundary), analyze the sound afterwards.
          const said = speech ? speech.take() : null;
          const text = triggerText ? `${triggerText} ${said ?? ""}`.trim() : said;
          triggerText = "";
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
      source.cancel();
      speech?.stop();
      socket?.close();
    };
    cancelRef.current = cancel;

    // Stop early and send what we have: the chunk in progress goes out (shorter than
    // usual), then "end" closes the report, which the server marks as ended early.
    finishRef.current = () => {
      if (finished || cancelled) return;
      finishRef.current = null;
      setStopping(true);
      clearInterval(ticker);
      setSecondsLeft(0);
      source.finish();
    };

    const abort = (key: StatusKey, message?: string): void => {
      if (finished || cancelled) return;
      finished = true;
      finishRef.current = null;
      cancel();
      setStopping(false);
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
          finishRef.current = null;
          clearInterval(ticker);
          speech?.stop();
          setStopping(false);
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


  helpRef.current = handleHelp;

  const active = capturing;
  const sent = status === "SENT_TO_DISPATCH";
  const totalSeconds = Math.round(totalMs / 1000);
  const progress = active ? (totalSeconds - secondsLeft) / totalSeconds : sent ? 1 : 0;

  const capabilityNotes: string[] = [];
  if (!demo) {
    if (!speechOk) capabilityNotes.push("This browser can’t transcribe speech, so only sounds will be used.");
    if (soundStatus === "unavailable")
      capabilityNotes.push("Sound detection couldn’t load, so only speech will be used.");
  }

  let hint: string;
  if (active) hint = "Say what’s happening. Stop whenever you’re done.";
  else if (sent) hint = "A responder is reviewing it. Tap Help to start a new report.";
  else if (voiceTrigger && voiceTriggerAvailable) hint = "Tap the button, or just say “Help”.";
  else hint = "Tap once. We listen for up to a minute and share your location.";

  return (
    <div className="caller-page">
      <main className="caller">
        <header className="caller-head">
          <span className="brand">
            <span className="brand-mark" aria-hidden="true" />
            Help Router
          </span>
          <span className="tag tag-demo">Demo</span>
        </header>

        {/* First thing on the page: if the trigger is off, saying "Help" does nothing,
            and the caller must be able to see that before they need it. */}
        {voiceTriggerAvailable && (
          <div className={`card-surface setting ${voiceTrigger ? "setting-on" : "setting-off"}`}>
            <span className="setting-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <rect x="9" y="3" width="6" height="11" rx="3" fill="currentColor" />
                <path
                  d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                />
              </svg>
            </span>
            <div className="setting-text">
              <p className="setting-title" id="voice-trigger-label">
                Voice trigger {voiceTrigger ? "on" : "off"}
              </p>
              <p className="setting-desc" role="status">
                {voiceTrigger
                  ? active
                    ? "Paused while listening."
                    : "Say “Help” to start a report hands-free."
                  : "Saying “Help” won’t start a report. Turn this on to go hands-free."}
              </p>
              {voiceTriggerError && (
                <p className="setting-error" role="alert">
                  {voiceTriggerError}
                </p>
              )}
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={voiceTrigger}
              aria-label="Voice trigger"
              className="switch"
              onClick={toggleVoiceTrigger}
              disabled={active}
            >
              <span className="switch-thumb" aria-hidden="true" />
            </button>
          </div>
        )}

        <p className="notice" role="note">
          Demo only. No real emergency service is contacted. A human confirms every dispatch.
        </p>

        {demo && (
          <div className="card-surface demo-controls">
            <label className="field">
              <span className="field-label">Scripted scenario</span>
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
            <p className="fine">Demo mode plays a scripted scenario and does not use your microphone.</p>
          </div>
        )}

        <section className="hero" aria-label="Get help">
          <div className={`help-wrap${active ? " is-active" : ""}${sent ? " is-sent" : ""}`}>
            <svg className="ring" viewBox="0 0 100 100" aria-hidden="true">
              <circle className="ring-track" cx="50" cy="50" r="47" />
              <circle
                className="ring-progress"
                cx="50"
                cy="50"
                r="47"
                pathLength={100}
                strokeDasharray="100"
                strokeDashoffset={100 - progress * 100}
                // A round line cap would draw a dot at 0%; hide the arc until it has length.
                opacity={progress > 0 ? 1 : 0}
              />
            </svg>
            <button
              className="help-button"
              onClick={() => void handleHelp()}
              disabled={active}
              aria-label="Press for help. Listens for up to 60 seconds and shares your location."
            >
              {active ? (
                <span className="help-inner">
                  <span className="help-count">{stopping ? "…" : secondsLeft}</span>
                  <span className="help-sub">{stopping ? "sending" : "seconds left"}</span>
                </span>
              ) : (
                <span className="help-inner">
                  <span className="help-word">Help</span>
                  <span className="help-sub">                    {sent
                      ? "start again"
                      : voiceTrigger && voiceTriggerAvailable
                        ? "tap or say it"
                        : "tap once"}</span>
                </span>
              )}
            </button>
          </div>

          <div className="status-block">
            <p className={`status${error ? " status-error" : ""}`} role="status" aria-live="polite">
              {error ? "Couldn’t finish the report" : STATUS_KEYS[status]}
            </p>
            {!error && <p className="hint">{hint}</p>}
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
          </div>

          {active && (
            <button
              type="button"
              className="stop-button"
              onClick={() => finishRef.current?.()}
              disabled={stopping}
            >
              <span className="stop-icon" aria-hidden="true" />
              {stopping ? "Sending what we have…" : "Stop and send"}
            </button>
          )}
        </section>

        {decision && <RouteSummary decision={decision} />}
        <HeardPanel chunks={heard} />

        {(capabilityNotes.length > 0 || chunkMs !== 10_000) && (
          <div className="notes-list">
            {chunkMs !== 10_000 && (
              <p className="fine">Fast mode: {chunkMs / 1000}s chunks instead of 10s.</p>
            )}
            {capabilityNotes.map((note) => (
              <p key={note} className="fine" role="status">
                {note}
              </p>
            ))}
          </div>
        )}

        {!demo && (
          <footer className="fine privacy">
            Your browser turns speech into text (Chrome uses Google’s speech service) and sounds
            are analysed on this device. We receive only the text and sound labels, not audio.
            {voiceTrigger &&
              " While the voice trigger is on, the browser’s speech service hears everything near the phone, even before you say Help. Nothing reaches us until you do."}
          </footer>
        )}
      </main>
    </div>
  );
}
