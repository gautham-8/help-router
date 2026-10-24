import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { dashboardToken } from "../src/lib/api";
import {
  DEFAULT_CHUNK_MS,
  MIN_CHUNK_MS,
  nextBackoffMs,
  parseChunkMs,
  secondsRemaining,
} from "../src/lib/timing";

describe("parseChunkMs", () => {
  it("defaults to the real 10s chunk", () => {
    expect(parseChunkMs("")).toBe(DEFAULT_CHUNK_MS);
    expect(parseChunkMs("?other=1")).toBe(DEFAULT_CHUNK_MS);
    expect(parseChunkMs("?chunkMs=")).toBe(DEFAULT_CHUNK_MS);
  });

  it("accepts a shorter chunk for fast demos", () => {
    expect(parseChunkMs("?chunkMs=2000")).toBe(2000);
  });

  it("ignores garbage and clamps to [MIN, DEFAULT]", () => {
    expect(parseChunkMs("?chunkMs=abc")).toBe(DEFAULT_CHUNK_MS);
    expect(parseChunkMs("?chunkMs=Infinity")).toBe(DEFAULT_CHUNK_MS);
    expect(parseChunkMs("?chunkMs=5")).toBe(MIN_CHUNK_MS);
    expect(parseChunkMs("?chunkMs=-4000")).toBe(MIN_CHUNK_MS);
    expect(parseChunkMs("?chunkMs=999999")).toBe(DEFAULT_CHUNK_MS);
  });

  it("property: always an integer within [MIN, DEFAULT], whatever the input", () => {
    fc.assert(
      fc.property(fc.string(), (raw) => {
        const ms = parseChunkMs(`?chunkMs=${encodeURIComponent(raw)}`);
        expect(Number.isInteger(ms)).toBe(true);
        expect(ms).toBeGreaterThanOrEqual(MIN_CHUNK_MS);
        expect(ms).toBeLessThanOrEqual(DEFAULT_CHUNK_MS);
      }),
    );
  });
});

describe("nextBackoffMs", () => {
  it("doubles then caps at 10s", () => {
    expect([0, 1, 2, 3, 4, 5].map(nextBackoffMs)).toEqual([1000, 2000, 4000, 8000, 10000, 10000]);
  });

  it("property: positive, capped, and non-decreasing", () => {
    fc.assert(
      fc.property(fc.integer({ min: -5, max: 500 }), (attempt) => {
        const ms = nextBackoffMs(attempt);
        expect(ms).toBeGreaterThan(0);
        expect(ms).toBeLessThanOrEqual(10_000);
        expect(nextBackoffMs(attempt + 1)).toBeGreaterThanOrEqual(ms);
      }),
    );
  });
});

describe("secondsRemaining", () => {
  it("rounds up and never goes negative", () => {
    expect(secondsRemaining(60_000, 0)).toBe(60);
    expect(secondsRemaining(60_000, 59_100)).toBe(1);
    expect(secondsRemaining(60_000, 61_000)).toBe(0);
  });
});

describe("dashboardToken", () => {
  it("reads ?token= and is empty otherwise", () => {
    expect(dashboardToken("?token=abc123")).toBe("abc123");
    expect(dashboardToken("?x=1")).toBe("");
    expect(dashboardToken("")).toBe("");
  });
});
