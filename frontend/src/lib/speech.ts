// On-device speech-to-text via the browser's Web Speech API.
//
// PRIVACY: the browser decides where recognition runs. In Chrome the audio is sent to
// Google's speech service; Safari uses Apple's. This app only forwards the resulting
// TEXT to its own server (no audio), and the UI tells the caller so.

export interface SpeechResultLike {
  text: string;
  isFinal: boolean;
}

// Splits a continuous recognition stream into per-chunk text.
//
// A continuous recognizer keeps one growing list of results (finished sentences plus a
// still-changing interim one). Each chunk wants only what was said since the last chunk,
// without losing words when the recognizer restarts mid-capture. Words that are still
// interim at a boundary are counted in the chunk where they were first seen.
export class TranscriptBuffer {
  private results: string[] = [];
  private consumed = 0;
  private carried: string[] = [];

  // Replace the current snapshot of results (as reported by the recognizer).
  update(results: SpeechResultLike[]): void {
    this.results = results.map((r) => r.text.trim());
  }

  // The recognizer restarted, so its result list starts over. Keep unread words.
  restart(): void {
    this.carried.push(...this.unread());
    this.results = [];
    this.consumed = 0;
  }

  // Text heard since the previous take(), then mark it as read.
  take(): string {
    const text = [...this.carried, ...this.unread()].filter(Boolean).join(" ");
    this.carried = [];
    this.consumed = this.results.length;
    return text;
  }

  private unread(): string[] {
    return this.results.slice(this.consumed);
  }
}

// Minimal shapes for the parts of the Web Speech API we use (not in every TS DOM lib).
interface RecognitionResultLike {
  isFinal: boolean;
  0: { transcript: string };
}
interface RecognitionEventLike {
  results: ArrayLike<RecognitionResultLike>;
}
interface RecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((e: RecognitionEventLike) => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  start(): void;
  stop(): void;
  abort?(): void;
}
type RecognitionCtor = new () => RecognitionLike;

function recognitionCtor(): RecognitionCtor | null {
  const w = window as unknown as {
    SpeechRecognition?: RecognitionCtor;
    webkitSpeechRecognition?: RecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function speechSupported(): boolean {
  return typeof window !== "undefined" && recognitionCtor() !== null;
}

export interface SpeechSession {
  // Words heard since the last call. "" = heard nothing; null = recognition is not
  // working (denied or failing), which a responder should see as "no transcript".
  take(): string | null;
  stop(): void;
}

// Errors that mean recognition cannot work at all, so retrying is pointless.
const FATAL_ERRORS = new Set(["not-allowed", "service-not-allowed", "language-not-supported"]);
const MAX_RESTARTS_WITHOUT_RESULTS = 8;

export function startSpeech(lang: string = navigator.language || "en-US"): SpeechSession | null {
  const Ctor = recognitionCtor();
  if (!Ctor) return null;

  const buffer = new TranscriptBuffer();
  const recognition = new Ctor();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = lang;

  let stopped = false;
  let failed = false;
  let restartsWithoutResults = 0;

  recognition.onresult = (event) => {
    restartsWithoutResults = 0;
    buffer.update(
      Array.from(event.results, (r) => ({ text: r[0].transcript, isFinal: r.isFinal })),
    );
  };
  recognition.onerror = (event) => {
    if (FATAL_ERRORS.has(event.error)) failed = true;
  };
  // Recognizers end on their own (silence, network blips). Keep listening until stopped.
  recognition.onend = () => {
    if (stopped || failed) return;
    restartsWithoutResults += 1;
    if (restartsWithoutResults > MAX_RESTARTS_WITHOUT_RESULTS) {
      failed = true;
      return;
    }
    buffer.restart();
    setTimeout(() => {
      if (stopped || failed) return;
      try {
        recognition.start();
      } catch {
        failed = true;
      }
    }, 250);
  };

  try {
    recognition.start();
  } catch {
    return null;
  }

  return {
    take: () => (failed ? null : buffer.take()),
    stop: () => {
      stopped = true;
      try {
        recognition.stop();
      } catch {
        // already stopped
      }
    },
  };
}

// ---- Voice trigger ("Help" as a wake word) ----
//
// Whole word only, so "helpful" or "helped" do not start a capture. Ordinary sentences
// like "can you help me" will; a false alarm costs less than a missed emergency, and a
// human confirms every dispatch.
const WAKE_WORD = /\bhelp\b/i;

// The text from the wake word onward ("help there's a fire"), or null if it was not said.
// Keeping the words after "help" means the first chunk does not lose them.
export function findWakeWord(text: string): string | null {
  const match = WAKE_WORD.exec(text);
  return match ? text.slice(match.index).trim() : null;
}

export interface WakeListener {
  stop(): void;
}

const WAKE_RETRY_MIN_MS = 250;
const WAKE_RETRY_MAX_MS = 5_000;
const WAKE_HEALTHY_SESSION_MS = 3_000;

// Listens until "help" is heard, then stops itself and calls onWake with what was said.
// Unlike a capture session it keeps restarting through long silences (that is the normal
// idle case). onUnavailable fires if recognition cannot work at all (e.g. permission denied).
export function listenForWakeWord(
  onWake: (heard: string) => void,
  onUnavailable: () => void,
  lang: string = navigator.language || "en-US",
): WakeListener | null {
  const Ctor = recognitionCtor();
  if (!Ctor) return null;

  const recognition = new Ctor();
  recognition.continuous = true;
  recognition.interimResults = true; // interim results trigger faster than final ones
  recognition.lang = lang;

  let stopped = false;
  let retryMs = WAKE_RETRY_MIN_MS;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;

  const halt = (): void => {
    stopped = true;
    if (retryTimer) clearTimeout(retryTimer);
    try {
      // abort() releases the recognizer immediately, so a capture session can start.
      if (recognition.abort) recognition.abort();
      else recognition.stop();
    } catch {
      // already stopped
    }
  };

  recognition.onresult = (event) => {
    if (stopped) return;
    retryMs = WAKE_RETRY_MIN_MS;
    const text = Array.from(event.results, (r) => r[0].transcript).join(" ");
    const heard = findWakeWord(text);
    if (heard !== null) {
      halt();
      onWake(heard);
    }
  };
  recognition.onerror = (event) => {
    if (FATAL_ERRORS.has(event.error) && !stopped) {
      halt();
      onUnavailable();
    }
  };
  // Recognizers end on their own after silence or network blips; keep listening, backing
  // off if it keeps failing so a broken service is not hammered.
  recognition.onend = () => {
    if (stopped) return;
    // A session that ran a while just timed out on silence; only quick failures back off.
    if (Date.now() - startedAt > WAKE_HEALTHY_SESSION_MS) retryMs = WAKE_RETRY_MIN_MS;
    retryTimer = setTimeout(() => {
      if (stopped) return;
      try {
        begin();
      } catch {
        halt();
        onUnavailable();
      }
    }, retryMs);
    retryMs = Math.min(retryMs * 2, WAKE_RETRY_MAX_MS);
  };

  let startedAt = 0;
  const begin = (): void => {
    startedAt = Date.now();
    recognition.start();
  };

  try {
    begin();
  } catch {
    return null;
  }
  return { stop: halt };
}
