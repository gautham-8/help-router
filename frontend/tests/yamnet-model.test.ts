// @vitest-environment node
//
// Runs the production sound code against the real vendored YAMNet files (CPU backend),
// so a corrupt model, a wrong class mapping, or reading the wrong model output fails here.

import * as tf from "@tensorflow/tfjs";
import { beforeAll, describe, expect, it } from "vitest";
import {
  buildClassIndex,
  CLASS_COUNT,
  parseClassMap,
  scoresToEvents,
  scoreWaveform,
} from "../src/lib/sounds";
import {
  diskModelHandler,
  readClassMapCsv,
  silence,
  sirenWail,
  smokeAlarm,
} from "./helpers/model";

const classIndex = buildClassIndex(parseClassMap(readClassMapCsv()));
let model: tf.GraphModel;

beforeAll(async () => {
  await tf.setBackend("cpu");
  await tf.ready();
  model = await tf.loadGraphModel(diskModelHandler());
}, 60_000);

async function eventsFor(wave: Float32Array) {
  return scoresToEvents(await scoreWaveform(tf, model, wave), classIndex);
}

describe("vendored YAMNet", () => {
  it("returns one 521-class score row per ~0.48 s frame, all valid probabilities", async () => {
    const scores = await scoreWaveform(tf, model, silence(3));
    expect(scores.length).toBeGreaterThanOrEqual(5);
    for (const row of scores) {
      expect(row).toHaveLength(CLASS_COUNT);
      expect(row.every((s) => s >= 0 && s <= 1)).toBe(true);
    }
  }, 60_000);

  it("hears nothing notable in silence", async () => {
    expect(await eventsFor(silence(4))).toEqual([]);
  }, 60_000);

  it("recognizes a smoke-alarm beep pattern", async () => {
    const events = await eventsFor(smokeAlarm(6));
    const smoke = events.find((e) => e.kind === "smoke_alarm");
    expect(smoke, JSON.stringify(events)).toBeDefined();
    expect(smoke!.confidence).toBeGreaterThan(0.5);
  }, 60_000);

  it("flags a siren-style wail as an alarm-type sound", async () => {
    const kinds = (await eventsFor(sirenWail(6))).map((e) => e.kind);
    expect(kinds.some((k) => k === "siren" || k === "alarm_generic")).toBe(true);
  }, 60_000);

  it("pads clips shorter than one patch instead of failing", async () => {
    const scores = await scoreWaveform(tf, model, silence(0.2));
    expect(scores.length).toBeGreaterThanOrEqual(1);
  }, 60_000);
});
