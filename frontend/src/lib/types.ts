// Shared domain types, mirroring backend/app/domain/models.py.

export type Service = "police" | "fire" | "medical";
export const ALL_SERVICES: Service[] = ["police", "fire", "medical"];

// A dashboard column: one per service, plus "triage" for reports the system could not
// classify (a human sends them to a service or dismisses them).
export type QueueName = Service | "triage";
export const ALL_QUEUES: QueueName[] = ["triage", ...ALL_SERVICES];

export type RouteStatus = "provisional" | "refined";

export type CaptureState =
  | "idle"
  | "listening"
  | "provisional"
  | "refined"
  | "closed";

export interface AudioEventView {
  kind: string;
  confidence: number;
}

export interface RouteDecisionView {
  services: Partial<Record<Service, number>>;
  status: RouteStatus;
  needs_attention: boolean;
  notes: string[];
  pinned?: Service[];
}

export interface LocationView {
  lat: number | null;
  lon: number | null;
  accuracy_m: number | null;
  known: boolean;
}

export interface DispatchView {
  report_id: string;
  service: QueueName;
  confirmed: boolean;
  rejected: boolean;
  responder: string | null;
  decided_at: string | null;
}

export interface QueueEntryView {
  report_id: string;
  service: QueueName;
  confidence: number;
  route_status: RouteStatus;
  needs_attention: boolean;
  notes: string[];
  transcript: string;
  events: AudioEventView[];
  missing_signals?: string[];
  location: LocationView;
  dispatch: DispatchView;
  created_at: string;
}

export interface ScenarioInfo {
  id: string;
  label: string;
  summary: string;
}

// Stable status keys used by the caller UI (also useful for screen readers / i18n).
export const STATUS_KEYS = {
  IDLE: "Ready",
  LISTENING: "Listening…",
  PROVISIONAL_ROUTE: "Provisional route",
  REFINED_ROUTE: "Final route, wrapping up…",
  SENT_TO_DISPATCH: "Sent to dispatch",
  MIC_DENIED: "Microphone access is required. Allow it in your browser settings and try again.",
  MIC_UNAVAILABLE:
    "This page cannot use the microphone. Open it over HTTPS (or on localhost) and try again.",
  CONNECTION_LOST: "Connection lost. Your report was sent as far as it got.",
  ERROR: "Something went wrong",
} as const;

export type StatusKey = keyof typeof STATUS_KEYS;
