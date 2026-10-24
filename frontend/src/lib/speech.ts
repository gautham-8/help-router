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
