import { useEffect, useState } from "react";
import {
  assignFromTriage,
  confirmDispatch,
  dashboardToken,
  openDashboardStream,
  rejectDispatch,
} from "../lib/api";
import { nextBackoffMs } from "../lib/timing";
import { ALL_QUEUES, type QueueEntryView, type QueueName, type Service } from "../lib/types";
import { QueueColumn } from "./QueueColumn";

type Queues = Record<QueueName, QueueEntryView[]>;
type Connection = "connecting" | "live" | "reconnecting" | "unauthorized";

const EMPTY: Queues = { triage: [], police: [], fire: [], medical: [] };
const RESPONDER = "dashboard-demo";
// Close code the server uses for a missing or wrong dashboard token.
const POLICY_VIOLATION = 1008;

const STAT_LABEL: Record<QueueName, string> = {
  triage: "Needs triage",
  police: "Police pending",
  fire: "Fire pending",
  medical: "Medical pending",
};

const CONNECTION_LABEL: Record<Connection, string> = {
  connecting: "Connecting…",
  live: "Live",
  reconnecting: "Reconnecting…",
  unauthorized: "Token required",
};

export function DashboardApp(): JSX.Element {
  const token = dashboardToken();
  const [queues, setQueues] = useState<Queues>(EMPTY);
  const [connection, setConnection] = useState<Connection>("connecting");
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;
    let stopped = false;

    const connect = (): void => {
      const ws = openDashboardStream(token);
      socket = ws;
      ws.onopen = () => {
        attempt = 0;
        setConnection("live");
        ws.send("hello"); // keeps the server read loop alive
      };
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        // Every update is a full snapshot of one queue, so a reconnect self-heals.
        if (msg.type === "queue_update") {
          setQueues((prev) => ({ ...prev, [msg.service as QueueName]: msg.queue }));
        }
      };
      ws.onclose = (ev) => {
        if (stopped) return;
        if (ev.code === POLICY_VIOLATION) {
          setConnection("unauthorized");
          return;
        }
        setConnection("reconnecting");
        timer = setTimeout(connect, nextBackoffMs(attempt));
        attempt += 1;
      };
    };

    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      socket?.close();
    };
  }, [token]);

  async function decide(
    action: typeof confirmDispatch,
    service: QueueName,
    reportId: string,
  ): Promise<void> {
    try {
      await action(reportId, service as Service, RESPONDER, token);
      setActionError(null);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Could not save that decision");
    }
  }

  async function assign(reportId: string, service: Service): Promise<void> {
    try {
      await assignFromTriage(reportId, service, RESPONDER, token);
      setActionError(null);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Could not save that decision");
    }
  }

  const pending = (name: QueueName): number =>
    queues[name].filter((e) => !e.dispatch.confirmed && !e.dispatch.rejected).length;

  return (
    <main className="dashboard">
      <header className="dash-head">
        <div className="dash-title">
          <span className="brand">
            <span className="brand-mark" aria-hidden="true" />
            Help Router
          </span>
          <h1>Dispatch</h1>
        </div>
        <p className="notice notice-inline" role="note">
          Demo only. No real emergency service is contacted.
        </p>
        <span className={`conn conn-${connection}`} role="status">
          <span className="conn-dot" aria-hidden="true" />
          {CONNECTION_LABEL[connection]}
        </span>
      </header>

      <ul className="stats" aria-label="Awaiting a decision">
        {ALL_QUEUES.map((name) => (
          <li key={name} className={`stat stat-${name}`}>
            <span className="stat-value">{pending(name)}</span>
            <span className="stat-label">
              <span className={`svc-dot svc-${name}`} aria-hidden="true" />
              {STAT_LABEL[name]}
            </span>
          </li>
        ))}
      </ul>

      {connection === "unauthorized" && (
        <p className="error" role="alert">
          This dashboard needs an access token. Open it as /dashboard?token=…
        </p>
      )}
      {actionError && (
        <p className="error" role="alert">
          {actionError}
        </p>
      )}
      <div className="columns">
        {ALL_QUEUES.map((name) => (
          <QueueColumn
            key={name}
            service={name}
            entries={queues[name]}
            onConfirm={(s, id) => void decide(confirmDispatch, s, id)}
            onReject={(s, id) => void decide(rejectDispatch, s, id)}
            onAssign={(id, s) => void assign(id, s)}
          />
        ))}
      </div>
    </main>
  );
}
