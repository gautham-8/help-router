// REST + WebSocket helpers for the Help Router backend.

import type { QueueEntryView, QueueName, ScenarioInfo, Service } from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function wsUrl(path: string): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}${path}`;
}

// The dashboard token (when the backend requires one) comes from `?token=...`.
export function dashboardToken(search: string = window.location.search): string {
  return new URLSearchParams(search).get("token") ?? "";
}

function tokenHeaders(token: string): Record<string, string> {
  return token ? { "X-Dashboard-Token": token } : {};
}

async function ensureOk(res: Response, fallback: string): Promise<Response> {
  if (res.ok) return res;
  let detail = fallback;
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") detail = body.detail;
  } catch {
    // keep the fallback message
  }
  throw new ApiError(detail, res.status);
}

export async function fetchScenarios(): Promise<ScenarioInfo[]> {
  const res = await ensureOk(await fetch("/scenarios"), "Failed to load scenarios");
  return res.json();
}

export interface CreateReportInput {
  scenario?: string;
  lat?: number;
  lon?: number;
  accuracy_m?: number;
}

export async function createReport(
  input: CreateReportInput,
): Promise<{ id: string; demo_safety: string }> {
  const res = await ensureOk(
    await fetch("/reports", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
    "Failed to start the report",
  );
  return res.json();
}

export async function fetchQueue(service: QueueName, token = ""): Promise<QueueEntryView[]> {
  const res = await ensureOk(
    await fetch(`/queues/${service}`, { headers: tokenHeaders(token) }),
    `Failed to load the ${service} queue`,
  );
  return res.json();
}

async function decide(
  action: "confirm" | "reject",
  reportId: string,
  service: QueueName,
  responder: string,
  token: string,
): Promise<void> {
  const url = `/reports/${encodeURIComponent(reportId)}/${service}/${action}?responder=${encodeURIComponent(responder)}`;
  await ensureOk(
    await fetch(url, { method: "POST", headers: tokenHeaders(token) }),
    `Could not ${action} this dispatch`,
  );
}

export function confirmDispatch(
  reportId: string,
  service: Service,
  responder: string,
  token = "",
): Promise<void> {
  return decide("confirm", reportId, service, responder, token);
}

export function rejectDispatch(
  reportId: string,
  service: QueueName,
  responder: string,
  token = "",
): Promise<void> {
  return decide("reject", reportId, service, responder, token);
}

// Send an unclassified report from triage to a service queue (a human decision).
export async function assignFromTriage(
  reportId: string,
  service: Service,
  responder: string,
  token = "",
): Promise<void> {
  const url = `/reports/${encodeURIComponent(reportId)}/triage/assign?service=${service}&responder=${encodeURIComponent(responder)}`;
  await ensureOk(
    await fetch(url, { method: "POST", headers: tokenHeaders(token) }),
    "Could not send this report to that service",
  );
}

export function openCaptureStream(reportId: string): WebSocket {
  return new WebSocket(wsUrl(`/ws/reports/${encodeURIComponent(reportId)}/stream`));
}

export function openDashboardStream(token = ""): WebSocket {
  const query = token ? `?token=${encodeURIComponent(token)}` : "";
  return new WebSocket(wsUrl(`/ws/dashboard${query}`));
}
