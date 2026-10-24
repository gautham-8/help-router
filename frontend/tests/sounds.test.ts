import fc from "fast-check";
import { describe, expect, it } from "vitest";
import {
  buildClassIndex,
  CLASS_COUNT,
  EVENT_MIN_CONFIDENCE,
  KIND_CLASSES,
  parseClassMap,
  scoresToEvents,
  type ClassIndex,
  type EventKind,
} from "../src/lib/sounds";
import { readClassMapCsv } from "./helpers/model";

const names = parseClassMap(readClassMapCsv());

describe("parseClassMap (vendored yamnet_class_map.csv)", () => {
  it("reads all 521 classes in index order", () => {
    expect(names).toHaveLength(CLASS_COUNT);
    expect(names.every((n) => typeof n === "string" && n.length > 0)).toBe(true);
    expect(names[0]).toBe("Speech");
  });

  it("keeps quoted names that contain commas", () => {
    expect(names).toContain("Smoke detector, smoke alarm");
    expect(names).toContain("Fire engine, fire truck (siren)");
  });

  it("rejects garbage instead of guessing", () => {
    expect(() => parseClassMap("index,mid,display_name\nnot a row")).toThrow();
  });
});

describe("buildClassIndex", () => {
  it("finds every class the event mapping relies on", () => {
    const index = buildClassIndex(names);
    for (const kind of Object.keys(KIND_CLASSES) as EventKind[]) {
      expect(index[kind]).toHaveLength(KIND_CLASSES[kind].length);
      index[kind].forEach((i, n) => expect(names[i]).toBe(KIND_CLASSES[kind][n]));
    }
  });

  it("fails loudly when a class is missing (e.g. a different model version)", () => {
    expect(() => buildClassIndex(["Speech", "Music"])).toThrow(/not found/);
  });
});

describe("scoresToEvents", () => {
  const index = buildClassIndex(names);
  const frame = (hits: Record<string, number>): number[] => {
    const row = new Array<number>(CLASS_COUNT).fill(0);
    for (const [name, score] of Object.entries(hits)) row[names.indexOf(name)] = score;
    return row;
  };

  it("reports the strongest reading of a kind across all frames and its classes", () => {
    const events = scoresToEvents(
      [frame({ Siren: 0.3 }), frame({ "Police car (siren)": 0.8 }), frame({ Siren: 0.5 })],
      index,
    );
    expect(events).toEqual([{ kind: "siren", confidence: 0.8 }]);
  });

  it("drops weak detections and sorts the rest strongest first", () => {
    const events = scoresToEvents(
      [frame({ Screaming: 0.6, "Smoke detector, smoke alarm": 0.9, Shatter: 0.1 })],
      index,
    );
    expect(events.map((e) => e.kind)).toEqual(["smoke_alarm", "scream"]);
  });

  it("returns nothing for silence or ordinary speech", () => {
    expect(scoresToEvents([frame({})], index)).toEqual([]);
    expect(scoresToEvents([frame({ Speech: 1 })], index)).toEqual([]);
    expect(scoresToEvents([], index)).toEqual([]);
  });

  it("property: one event per kind, confidences in [min, 1], sorted", () => {
    const scores = fc.array(
      fc.array(fc.double({ min: -0.5, max: 1.5, noNaN: true }), {
        minLength: CLASS_COUNT,
        maxLength: CLASS_COUNT,
      }),
      { maxLength: 6 },
    );
    fc.assert(
      fc.property(scores, (matrix) => {
        const events = scoresToEvents(matrix, index as ClassIndex);
        const kinds = events.map((e) => e.kind);
        expect(new Set(kinds).size).toBe(kinds.length);
        for (const e of events) {
          expect(e.confidence).toBeGreaterThanOrEqual(EVENT_MIN_CONFIDENCE);
          expect(e.confidence).toBeLessThanOrEqual(1);
        }
        for (let i = 1; i < events.length; i++) {
          expect(events[i - 1].confidence).toBeGreaterThanOrEqual(events[i].confidence);
        }
      }),
    );
  });
});
