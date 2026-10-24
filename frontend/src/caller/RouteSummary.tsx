import { type RouteDecisionView } from "../lib/types";
import { routedServices } from "../lib/route";

const SERVICE_LABEL: Record<string, string> = {
  police: "Police",
  fire: "Fire",
  medical: "Medical",
};

export function RouteSummary({ decision }: { decision: RouteDecisionView }): JSX.Element {
  const routed = routedServices(decision);
  const refined = decision.status === "refined";

  return (
    <section className="card-surface route-summary" aria-label="Routing result">
      <div className="route-head">
        <h2 className="section-title">Routing</h2>
        <span className={`tag ${refined ? "tag-refined" : "tag-provisional"}`}>
          {refined ? "Refined route" : "Provisional route"}
        </span>
      </div>
      {decision.needs_attention && (
        <p className="attention">No clear service yet — flagged for a responder.</p>
      )}
      <ul className="route-list">
        {routed.map((s) => {
          const pct = Math.round((decision.services[s] ?? 0) * 100);
          return (
            <li key={s}>
              <span className={`pill pill-${s} svc-${s}`}>{SERVICE_LABEL[s]}</span>
              <span className="meter" aria-hidden="true">
                <span className={`meter-fill svc-${s}`} style={{ width: `${pct}%` }} />
              </span>
              <span className="conf">{pct}%</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
