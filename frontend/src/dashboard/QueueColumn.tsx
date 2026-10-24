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

function receivedAt(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function PinIcon(): JSX.Element {
  return (
    <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="10" r="2.3" fill="currentColor" />
    </svg>
  );
}

export function QueueColumn({ service, entries, onConfirm, onReject, onAssign }: Props): JSX.Element {
  const triage = service === "triage";
  return (
    <section className={`queue queue-${service}`} aria-label={`${LABEL[service]} queue`}>
      <h2 className="queue-title">
        <span className={`svc-dot svc-${service}`} aria-hidden="true" />
        {LABEL[service]}
        <span className="count">{entries.length}</span>
      </h2>
      {triage && (
        <p className="queue-hint">
          The system could not tell which service these need. Send each to one, or dismiss it.
        </p>
      )}
      {entries.length === 0 && <p className="empty">No active reports.</p>}
      {entries.map((e) => {
        const pct = Math.round(e.confidence * 100);
        const events = summarizeEvents(e.events);
        return (
          <article
            key={e.report_id}
            className={`report${e.dispatch.confirmed ? " is-confirmed" : ""}`}
            aria-label={`Report ${e.report_id}`}
          >
            <div className="report-head">
              <span className={`badge badge-${e.route_status}`}>{e.route_status}</span>
              <span className="report-meta">
                {receivedAt(e.created_at)} · #{e.report_id.slice(0, 6)}
              </span>
            </div>

            {!triage && (
              <div className="report-conf">
                <span className="meter" aria-hidden="true">
                  <span className={`meter-fill svc-${service}`} style={{ width: `${pct}%` }} />
                </span>
                <span className="confidence">{pct}% confidence</span>
              </div>
            )}

            {e.needs_attention && !triage && <p className="attention">Needs attention</p>}

            <blockquote className="transcript">“{e.transcript || "…"}”</blockquote>

            {events.length > 0 && (
              <ul className="chips" aria-label="Sounds detected">
                {events.map((ev) => (
                  <li key={ev.kind} className="chip">
                    {ev.kind.replace(/_/g, " ")} ({Math.round(ev.confidence * 100)}%)
                  </li>
                ))}
              </ul>
            )}

            <p className="location">
              <PinIcon />
              {e.location.known ? (
                <a
                  href={`https://www.openstreetmap.org/?mlat=${e.location.lat}&mlon=${e.location.lon}#map=17/${e.location.lat}/${e.location.lon}`}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  {`${e.location.lat?.toFixed(4)}, ${e.location.lon?.toFixed(4)}`}
                </a>
              ) : (
                <span>location unknown</span>
              )}
              {e.location.known && e.location.accuracy_m !== null && (
                <span className="accuracy"> ±{Math.round(e.location.accuracy_m)} m</span>
              )}
            </p>

            {e.missing_signals && e.missing_signals.length > 0 && (
              <p className="notes">
                Unavailable from the caller’s device:{" "}
                {e.missing_signals.map((m) => MISSING_LABEL[m] ?? m).join(", ")}
              </p>
            )}
            {e.notes.length > 0 && <p className="notes">{e.notes.join("; ")}</p>}

            {triage ? (
              <div className="actions actions-wrap">
                {ALL_SERVICES.map((s) => (
                  <button
                    key={s}
                    type="button"
                    className={`btn btn-assign assign-${s}`}
                    onClick={() => onAssign?.(e.report_id, s)}
                  >
                    Send to {LABEL[s]}
                  </button>
                ))}
                <button type="button" className="btn btn-ghost" onClick={() => onReject(service, e.report_id)}>
                  Dismiss
                </button>
              </div>
            ) : e.dispatch.confirmed ? (
              <p className="decided">Dispatch confirmed by {e.dispatch.responder}</p>
            ) : (
              <div className="actions">
                <button
                  type="button"
                  className="btn btn-confirm"
                  onClick={() => onConfirm(service, e.report_id)}
                >
                  Confirm dispatch
                </button>
                <button type="button" className="btn btn-ghost" onClick={() => onReject(service, e.report_id)}>
                  Reject
                </button>
              </div>
            )}
          </article>
        );
      })}
    </section>
  );
}
