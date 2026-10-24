// Test helpers: load the vendored YAMNet from disk and synthesize waveforms.

import fs from "node:fs";
import path from "node:path";
import type * as TF from "@tensorflow/tfjs";

export const MODEL_DIR = path.resolve(__dirname, "../../public/models/yamnet");
export const SAMPLE_RATE = 16_000;

export function readClassMapCsv(): string {
  return fs.readFileSync(path.join(MODEL_DIR, "yamnet_class_map.csv"), "utf8");
}

// An IOHandler that reads model.json and its weight shards straight from disk, so the
// tests exercise the exact files the browser downloads.
export function diskModelHandler(): TF.io.IOHandler {
  return {
    load: async () => {
      const json = JSON.parse(fs.readFileSync(path.join(MODEL_DIR, "model.json"), "utf8"));
      const shards: Buffer[] = json.weightsManifest
        .flatMap((group: { paths: string[] }) => group.paths)
        .map((p: string) => fs.readFileSync(path.join(MODEL_DIR, p)));
      const all = Buffer.concat(shards);
      return {
        modelTopology: json.modelTopology,
        weightSpecs: json.weightsManifest.flatMap((g: { weights: unknown[] }) => g.weights),
        weightData: all.buffer.slice(all.byteOffset, all.byteOffset + all.byteLength),
        format: json.format,
        generatedBy: json.generatedBy,
        convertedBy: json.convertedBy,
      } as TF.io.ModelArtifacts;
    },
  };
}

function makeWave(seconds: number, sample: (t: number) => number): Float32Array {
  const wave = new Float32Array(Math.round(seconds * SAMPLE_RATE));
  for (let i = 0; i < wave.length; i++) wave[i] = sample(i / SAMPLE_RATE);
  return wave;
}

export const silence = (seconds: number): Float32Array => makeWave(seconds, () => 0);

// Smoke detector: 3.1 kHz beeps, three 0.5 s beeps then a pause (the "T3" pattern).
export const smokeAlarm = (seconds: number): Float32Array =>
  makeWave(seconds, (t) =>
    t % 4 < 3 && t % 1 < 0.5 ? 0.7 * Math.sin(2 * Math.PI * 3100 * t) : 0,
  );

// Emergency-vehicle style wail: a tone sweeping 600-1400 Hz.
export const sirenWail = (seconds: number): Float32Array =>
  makeWave(seconds, (t) => 0.6 * Math.sin(2 * Math.PI * (1000 + 400 * Math.sin(2 * Math.PI * 0.25 * t)) * t));
