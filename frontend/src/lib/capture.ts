// Microphone + geolocation capture helpers for the caller app.

export interface GeoResult {
  lat: number | null;
  lon: number | null;
  accuracy_m: number | null;
  known: boolean;
}

const UNKNOWN_LOCATION: GeoResult = { lat: null, lon: null, accuracy_m: null, known: false };

export async function getLocation(): Promise<GeoResult> {
  if (!("geolocation" in navigator)) return UNKNOWN_LOCATION;
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        resolve({
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          accuracy_m: pos.coords.accuracy,
          known: true,
        }),
      // Requirement 1.4: proceed with unknown location on denial/unavailability.
      () => resolve(UNKNOWN_LOCATION),
      { enableHighAccuracy: true, timeout: 5000 },
    );
  });
}

// The user (or their browser policy) said no.
export class MicDeniedError extends Error {
  constructor() {
    super("microphone access denied");
    this.name = "MicDeniedError";
  }
}

// The page cannot ask at all. Browsers hide `navigator.mediaDevices` on insecure
// origins, e.g. a phone opening http://<laptop-ip>:5173.
export class MicUnavailableError extends Error {
  constructor() {
    super("microphone is unavailable on this page");
    this.name = "MicUnavailableError";
  }
}

// Browsers switch on echo cancellation, noise suppression and auto-gain by default. They
// are built for phone calls: they treat anything that is not a voice as noise and remove
// it, which is exactly the alarms, sirens, glass and screams we are listening for. Ask
// for the raw signal instead. (Speech recognition has its own capture and cleanup.)
export const RAW_AUDIO_CONSTRAINTS: MediaTrackConstraints = {
  echoCancellation: false,
  noiseSuppression: false,
  autoGainControl: false,
};

// Requests mic access (Requirement 1.3).
export async function requestMic(): Promise<MediaStream> {
  if (!navigator.mediaDevices?.getUserMedia) throw new MicUnavailableError();
  try {
    return await navigator.mediaDevices.getUserMedia({ audio: RAW_AUDIO_CONSTRAINTS });
  } catch {
    throw new MicDeniedError();
  }
}

const MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/mp4",
  "audio/webm",
  "audio/ogg;codecs=opus",
];

// First container the browser can record (Safari: mp4, Chrome/Firefox: webm/ogg).
export function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return MIME_CANDIDATES.find((type) => MediaRecorder.isTypeSupported(type));
}

// Controls for a running capture.
export interface CaptureControl {
  // Stop early but keep what was captured: the chunk in progress is emitted (shorter
  // than usual), then onDone fires as if the window had closed.
  finish(): void;
  // Abandon: no further chunks, no onDone. Releases the microphone.
  cancel(): void;
}

// Records `count` consecutive chunks of `chunkMs` each. A fresh MediaRecorder is used
// per chunk so every blob is a complete, independently decodable audio file (timesliced
// chunks after the first have no container header and cannot be decoded alone).
export function recordInChunks(
  stream: MediaStream,
  chunkMs: number,
  count: number,
  onChunk: (blob: Blob, index: number) => void,
  onDone: () => void,
): CaptureControl {
  const mimeType = pickMimeType();
  let index = 0;
  let cancelled = false;
  let finishing = false;
  let done = false;
  let current: MediaRecorder | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const releaseMic = (): void => stream.getTracks().forEach((t) => t.stop());

  const next = (): void => {
    if (cancelled || done) return;
    if (index >= count || finishing) {
      done = true;
      releaseMic();
      onDone();
      return;
    }
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    const parts: BlobPart[] = [];
    const chunkIndex = index;
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) parts.push(e.data);
    };
    recorder.onstop = () => {
      if (!cancelled) onChunk(new Blob(parts, { type: recorder.mimeType }), chunkIndex);
      index += 1;
      next();
    };
    current = recorder;
    recorder.start();
    timer = setTimeout(() => {
      if (recorder.state !== "inactive") recorder.stop();
    }, chunkMs);
  };

  next();

  return {
    finish: () => {
      if (cancelled || finishing || done) return;
      finishing = true;
      clearTimeout(timer);
      // Stopping the recorder emits the partial chunk via onstop, which then ends.
      if (current && current.state !== "inactive") current.stop();
      else next();
    },
    cancel: () => {
      cancelled = true;
      clearTimeout(timer);
      if (current && current.state !== "inactive") current.stop();
      releaseMic();
    },
  };
}

// Demo mode has no microphone: it just emits "chunk i is ready" on the same schedule a
// real recording would, so the scripted scenario plays at the real pace.
export function scheduleChunks(
  chunkMs: number,
  count: number,
  onChunk: (index: number) => void,
  onDone: () => void,
): CaptureControl {
  let index = 0;
  let done = false;
  const end = (): void => {
    done = true;
    clearInterval(timer);
    onDone();
  };
  const timer = setInterval(() => {
    onChunk(index);
    index += 1;
    if (index >= count) end();
  }, chunkMs);
  return {
    // Like a real recording, the chunk in progress still counts.
    finish: () => {
      if (done) return;
      onChunk(index);
      index += 1;
      end();
    },
    cancel: () => {
      done = true;
      clearInterval(timer);
    },
  };
}

// Base64 (no data-URL prefix) of a blob, for the JSON capture protocol.
export function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error("could not read audio"));
    reader.onload = () => {
      const result = String(reader.result);
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.readAsDataURL(blob);
  });
}
