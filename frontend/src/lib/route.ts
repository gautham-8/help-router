// Pure client-side helpers over a RouteDecisionView.

import {
  ALL_SERVICES,
  type AudioEventView,
  type RouteDecisionView,
  type Service,
} from "./types";

// Services present in the decision, in canonical order.
// One entry per sound kind (its strongest reading), strongest first. A minute of capture
// produces many repeats of the same kind; a responder wants the picture, not the log.
export function summarizeEvents(events: AudioEventView[]): AudioEventView[] {
  const best = new Map<string, number>();
  for (const e of events) best.set(e.kind, Math.max(best.get(e.kind) ?? 0, e.confidence));
  return [...best.entries()]
    .map(([kind, confidence]) => ({ kind, confidence }))
    .sort((a, b) => b.confidence - a.confidence || a.kind.localeCompare(b.kind));
}

export function routedServices(decision: RouteDecisionView): Service[] {
  return ALL_SERVICES.filter((s) => decision.services[s] !== undefined);
}

// A decision needs attention exactly when nothing is routed.
export function derivedNeedsAttention(decision: RouteDecisionView): boolean {
  return routedServices(decision).length === 0;
}
