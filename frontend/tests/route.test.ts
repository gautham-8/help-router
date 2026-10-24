import { describe, expect, it } from "vitest";
import fc from "fast-check";
import { derivedNeedsAttention, routedServices } from "../src/lib/route";
import { ALL_SERVICES, type RouteDecisionView, type Service } from "../src/lib/types";

function makeDecision(services: Partial<Record<Service, number>>): RouteDecisionView {
  return {
    services,
    status: "provisional",
    needs_attention: Object.keys(services).length === 0,
    notes: [],
  };
}

describe("routedServices", () => {
  it("returns services in canonical order", () => {
    const d = makeDecision({ medical: 0.5, police: 0.9 });
    expect(routedServices(d)).toEqual(["police", "medical"]);
  });

  it("property: result is a subset of ALL_SERVICES, de-duplicated, canonical order", () => {
    const serviceConf = fc.record({
      police: fc.option(fc.float({ min: 0, max: 1 }), { nil: undefined }),
      fire: fc.option(fc.float({ min: 0, max: 1 }), { nil: undefined }),
      medical: fc.option(fc.float({ min: 0, max: 1 }), { nil: undefined }),
    });
    fc.assert(
      fc.property(serviceConf, (raw) => {
        const services: Partial<Record<Service, number>> = {};
        for (const s of ALL_SERVICES) {
          const v = raw[s];
          if (v !== undefined && v !== null) services[s] = v;
        }
        const result = routedServices(makeDecision(services));
        // subset
        expect(result.every((s) => ALL_SERVICES.includes(s))).toBe(true);
        // canonical order
        const ordered = ALL_SERVICES.filter((s) => result.includes(s));
        expect(result).toEqual(ordered);
        // needs-attention consistency
        expect(derivedNeedsAttention(makeDecision(services))).toBe(result.length === 0);
      }),
    );
  });
});
