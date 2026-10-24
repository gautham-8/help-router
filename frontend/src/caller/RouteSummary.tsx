import { type RouteDecisionView } from "../lib/types";
import { routedServices } from "../lib/route";

const SERVICE_LABEL: Record<string, string> = {
  police: "Police",
  fire: "Fire",
  medical: "Medical",
};

export function RouteSummary({ decision }: { decision: RouteDecisionView }): JSX.Element {
  const routed = routedServices(decision);

  return (
    <section className="route-summary" aria-label="Routing result">
      <p className="route-status">
        {decision.status === "refined" ? "Refined route" : "Provisional route"}
      </p>
      {decision.needs_attention && (
        <p className="attention">No clear service yet — flagged for a responder.</p>
      )}
      <ul>
        {routed.map((s) => (
          <li key={s}>
            <span className={`pill pill-${s}`}>{SERVICE_LABEL[s]}</span>
            <span className="conf">{Math.round((decision.services[s] ?? 0) * 100)}%</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
