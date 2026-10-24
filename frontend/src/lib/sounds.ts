// On-device sound-event detection with YAMNet (Google, Apache-2.0), run through
// TensorFlow.js. The model files are vendored in public/models/yamnet, so detection
// works offline and no audio is sent anywhere for this step.
//
// YAMNet scores 521 AudioSet classes per 0.48 s frame. We keep the handful that matter
// for dispatch and map them onto the event kinds the backend router understands.

import type * as TF from "@tensorflow/tfjs";
import { decodeTo16kMono } from "./audio";
import type { AudioEventView } from "./types";

export type EventKind =
  | "scream"
  | "glass_breaking"
  | "siren"
  | "smoke_alarm"
  | "explosion"
  | "alarm_generic";

// YAMNet display names behind each backend event kind. Names (not indices) so the map
// stays readable; a test checks every name exists in the vendored class list.
export const KIND_CLASSES: Record<EventKind, string[]> = {
  scream: ["Screaming", "Shout", "Yell"],
  glass_breaking: ["Shatter", "Glass"],
  siren: [
    "Siren",
    "Police car (siren)",
    "Ambulance (siren)",
    "Fire engine, fire truck (siren)",
    "Civil defense siren",
    "Emergency vehicle",
  ],
  smoke_alarm: ["Smoke detector, smoke alarm", "Fire alarm"],
  explosion: ["Explosion"],
  alarm_generic: ["Alarm"],
};

export const MODEL_BASE_URL = "/models/yamnet";
export const CLASS_COUNT = 521;
// YAMNet needs at least one 0.975 s patch (15,600 samples at 16 kHz).
export const MIN_SAMPLES = 15_600;
// Weaker detections are noise; do not send them to a responder.
export const EVENT_MIN_CONFIDENCE = 0.25;

export type ClassIndex = Record<EventKind, number[]>;

// Parses yamnet_class_map.csv ("index,mid,display_name", names may be quoted and may
// contain commas; the file uses CRLF line endings). Returns names by class index.
export function parseClassMap(csv: string): string[] {
  const names: string[] = [];
  for (const line of csv.split(/\r?\n/).slice(1)) {
    if (!line.trim()) continue;
    const match = line.match(/^(\d+),[^,]*,(?:"((?:[^"]|"")*)"|(.*))$/);
    if (!match) throw new Error(`unparseable class map line: ${line}`);
    names[Number(match[1])] = (match[2] ?? match[3]).replace(/""/g, '"');
  }
  return names;
}

// Resolves KIND_CLASSES to class indices; throws if a name is missing, so a typo or a
// different model version fails loudly instead of silently never detecting anything.
export function buildClassIndex(names: string[]): ClassIndex {
  const index = {} as ClassIndex;
  for (const kind of Object.keys(KIND_CLASSES) as EventKind[]) {
    index[kind] = KIND_CLASSES[kind].map((name) => {
      const i = names.indexOf(name);
      if (i < 0) throw new Error(`YAMNet class not found: ${name}`);
      return i;
    });
  }
  return index;
}

// Collapses per-frame class scores into at most one event per kind: the strongest score
// of any of that kind's classes over any frame, kept if it clears `minConfidence`.
export function scoresToEvents(
  scores: number[][],
  classIndex: ClassIndex,
  minConfidence: number = EVENT_MIN_CONFIDENCE,
): AudioEventView[] {
  const events: AudioEventView[] = [];
  for (const kind of Object.keys(classIndex) as EventKind[]) {
    let best = 0;
    for (const frame of scores) {
      for (const i of classIndex[kind]) {
        if (frame[i] > best) best = frame[i];
      }
    }
    const confidence = Math.min(1, Math.max(0, best));
    if (confidence >= minConfidence) {
      events.push({ kind, confidence: Math.round(confidence * 1000) / 1000 });
    }
  }
  return events.sort((a, b) => b.confidence - a.confidence);
}

function tensorsOf(output: unknown): TF.Tensor[] {
  if (Array.isArray(output)) return output as TF.Tensor[];
  if (output && typeof (output as TF.Tensor).shape !== "undefined") return [output as TF.Tensor];
  return Object.values(output as Record<string, TF.Tensor>);
}

// Runs YAMNet on a 16 kHz mono waveform and returns the [frames x 521] score matrix.
// The model has three outputs (spectrogram, embeddings, scores) in no promised order,
// so the scores are found by their 521-wide last dimension, not by position.
export async function scoreWaveform(
  tf: typeof TF,
  model: TF.GraphModel,
  waveform: Float32Array,
): Promise<number[][]> {
  let samples = waveform;
  if (samples.length < MIN_SAMPLES) {
    samples = new Float32Array(MIN_SAMPLES);
    samples.set(waveform);
  }
  const input = tf.tensor1d(samples);
  const outputs = tensorsOf(model.predict(input));
  try {
    const scores = outputs.find((t) => t.shape[t.shape.length - 1] === CLASS_COUNT);
    if (!scores) throw new Error("YAMNet scores output not found");
    return (await scores.array()) as number[][];
  } finally {
    tf.dispose([input, ...outputs]);
  }
}

export interface SoundDetector {
  detect(blob: Blob): Promise<AudioEventView[]>;
  dispose(): void;
}

// Loads TensorFlow.js (lazily, so the bundle for other pages stays small), the model,
// and the class map. Rejects if anything is missing; callers treat that as "sound
// detection unavailable" and carry on with speech alone.
export async function loadSoundDetector(baseUrl: string = MODEL_BASE_URL): Promise<SoundDetector> {
  const [tf, csv] = await Promise.all([
    import("@tensorflow/tfjs"),
    fetch(`${baseUrl}/yamnet_class_map.csv`).then((res) => {
      if (!res.ok) throw new Error(`could not load the class map (${res.status})`);
      return res.text();
    }),
  ]);
  const classIndex = buildClassIndex(parseClassMap(csv));
  await tf.ready();
  const model = await tf.loadGraphModel(`${baseUrl}/model.json`);
  // Warm-up run: compiles GPU shaders so the first real chunk is not slow.
  await scoreWaveform(tf, model, new Float32Array(MIN_SAMPLES));
  return {
    detect: async (blob) =>
      scoresToEvents(await scoreWaveform(tf, model, await decodeTo16kMono(blob)), classIndex),
    dispose: () => model.dispose(),
  };
}
