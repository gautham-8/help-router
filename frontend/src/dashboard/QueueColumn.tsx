import { summarizeEvents } from "../lib/route";
import { ALL_SERVICES, type QueueEntryView, type QueueName, type Service } from "../lib/types";

const LABEL: Record<QueueName, string> = {
  triage: "Needs triage",
  police: "Police",
  fire: "Fire",
  medical: "Medical",
};

const MISSING_LABEL: Record<string, string> = {
  transcript: "no speech transcript",
  audio_events: "no sound analysis",
};

interface Props {
  service: QueueName;
  entries: QueueEntryView[];
  onConfirm: (service: QueueName, reportId: string) => void;
  onReject: (service: QueueName, reportId: string) => void;
  onAssign?: (reportId: string, service: Service) => void;
}

export function QueueColumn({ service, entries, onConfirm, onReject, onAssign }: Props): JSX.Element {
  const triage = service === "triage";
  return (
    <section className={`queue queue-${service}`} aria-label={`${LABEL[service]} queue`}>
      <h2>
        {LABEL[service]} <span className="count">{entries.length}</span>
      </h2>
      {triage && (
        <p className="hint">
          The system could not tell which service these need. Send each to one, or dismiss it.
        </p>
      )}
      {entries.length === 0 && <p className="empty">No active reports.</p>}
      {entries.map((e) => (
        <article key={e.report_id} className="card">
          <div className="card-head">
            <span className={`badge badge-${e.route_status}`}>{e.route_status}</span>
            {!triage && (
              <span className="confidence">{Math.round(e.confidence * 100)}% confidence</span>
            )}
          </div>
          {e.needs_attention && !triage && <p className="attention">Needs attention</p>}
          <p className="transcript">“{e.transcript || "…"}”</p>
          {e.events.length > 0 && (
            <ul className="events">
              {summarizeEvents(e.events).map((ev) => (
                <li key={ev.kind}>
                  {ev.kind.replace(/_/g, " ")} ({Math.round(ev.confidence * 100)}%)
                </li>
              ))}
            </ul>
          )}
          {e.missing_signals && e.missing_signals.length > 0 && (
            <p className="notes">
              Unavailable from the caller’s device:{" "}
              {e.missing_signals.map((m) => MISSING_LABEL[m] ?? m).join(", ")}
            </p>
          )}
          <p className="location">
            {e.location.known
              ? `📍 ${e.location.lat?.toFixed(4)}, ${e.location.lon?.toFixed(4)}`
              : "📍 location unknown"}
          </p>
          {e.notes.length > 0 && <p className="notes">{e.notes.join("; ")}</p>}
          {triage ? (
            <div className="actions actions-wrap">
              {ALL_SERVICES.map((s) => (
                <button key={s} className={`assign assign-${s}`} onClick={() => onAssign?.(e.report_id, s)}>
                  Send to {LABEL[s]}
                </button>
              ))}
              <button className="reject" onClick={() => onReject(service, e.report_id)}>
                Dismiss
              </button>
            </div>
          ) : e.dispatch.confirmed ? (
            <p className="decided confirmed">Dispatch confirmed by {e.dispatch.responder}</p>
          ) : (
            <div className="actions">
              <button className="confirm" onClick={() => onConfirm(service, e.report_id)}>
                Confirm dispatch
              </button>
              <button className="reject" onClick={() => onReject(service, e.report_id)}>
                Reject
              </button>
            </div>
          )}
        </article>
      ))}
    </section>
  );
}
