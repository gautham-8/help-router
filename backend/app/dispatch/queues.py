"""In-memory dispatch queues and the human-confirmation workflow.

DEMO SAFETY: this module never contacts a real emergency service. There is
deliberately no integration with 911, a PSAP, or any external dispatch target.
``REAL_DISPATCH_ENABLED`` is a hard-off guard; confirming a report only records a
decision in memory.

Queues: one per service, plus ``triage``. A report the system could not classify (nothing
heard, speech recognition failing, ambiguous) goes to triage instead of vanishing: a
human sends it to a service queue or dismisses it. Sending it on is not a dispatch; the
service's own responder still has to confirm.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.domain.models import (
    ALL_QUEUES,
    DispatchStatus,
    QueueName,
    Report,
    RouteDecision,
    Service,
)

# Hard demo-safety guard. The codebase contains no real dispatch integration, and
# this flag must stay False. See Requirement 5.6.
REAL_DISPATCH_ENABLED: bool = False

TRIAGE: QueueName = "triage"


class DecisionConflict(ValueError):
    """Raised when a responder decision contradicts an earlier one."""


class QueueEntry:
    """A single (report, queue) item visible on a dashboard column."""

    def __init__(self, report: Report, queue: QueueName) -> None:
        self.report = report
        self.queue = queue
        self.status = DispatchStatus(report_id=report.id, service=queue)

    @property
    def confidence(self) -> float:
        """This queue's service confidence (0 for triage, which is not a service)."""
        for service, confidence in self.report.route.services.items():
            if service == self.queue:
                return confidence
        return 0.0

    def to_payload(self) -> dict[str, Any]:
        r = self.report
        return {
            "report_id": r.id,
            "service": self.queue,
            "confidence": self.confidence,
            "route_status": r.route.status,
            "needs_attention": r.route.needs_attention,
            "notes": r.route.notes,
            "transcript": " ".join(c.text for c in r.transcript_chunks).strip(),
            "events": [{"kind": e.kind, "confidence": e.confidence} for e in r.events],
            "missing_signals": r.missing_signals,
            "location": r.location.model_dump(),
            "dispatch": self.status.model_dump(mode="json"),
            "created_at": r.created_at.isoformat(),
        }


class DispatchHub:
    """Holds the dispatch queues and applies route decisions to them."""

    def __init__(self) -> None:
        # queue -> report_id -> entry
        self._queues: dict[QueueName, dict[str, QueueEntry]] = {q: {} for q in ALL_QUEUES}
        # (queue, report_id) pairs a responder dismissed, or already sent on from triage.
        # Later route updates must not bring them back into that queue.
        self._rejected: set[tuple[QueueName, str]] = set()

    def clear(self) -> None:
        for queue in self._queues.values():
            queue.clear()
        self._rejected.clear()

    def forget(self, report_id: str) -> None:
        """Drop every trace of a report (used when old reports are evicted)."""
        for name in ALL_QUEUES:
            self._queues[name].pop(report_id, None)
            self._rejected.discard((name, report_id))

    def apply_route(self, report: Report) -> list[QueueName]:
        """Fan a report's route decision out to the matching queues.

        A report goes to every service it routes to, or to triage when it routes to none.
        Entries are created or updated in place; an undecided entry is removed when the
        route stops including its queue, but a confirmed one stays. Dismissed
        (queue, report) pairs are never re-added. Returns the queues that changed.
        """
        decision: RouteDecision = report.route
        wanted: set[QueueName] = set(decision.services) or {TRIAGE}
        touched: list[QueueName] = []

        for name in ALL_QUEUES:
            if (name, report.id) in self._rejected:
                continue
            queue = self._queues[name]
            entry = queue.get(report.id)
            if name in wanted:
                if entry is None:
                    queue[report.id] = QueueEntry(report, name)
                else:
                    entry.report = report
                touched.append(name)
            elif entry is not None and not entry.status.confirmed:
                del queue[report.id]
                touched.append(name)
        return touched

    def snapshot(self, queue: QueueName) -> list[dict[str, Any]]:
        return [e.to_payload() for e in self._queues[queue].values()]

    def get_entry(self, queue: QueueName, report_id: str) -> QueueEntry | None:
        return self._queues[queue].get(report_id)

    def confirm(self, queue: QueueName, report_id: str, responder: str | None) -> DispatchStatus:
        """Record a human-confirmed dispatch. The only path to a dispatch."""
        if queue == TRIAGE:
            raise DecisionConflict("triage items are sent to a service or dismissed, not confirmed")
        entry = self._require(queue, report_id)
        # Demo mode: this records the decision only. REAL_DISPATCH_ENABLED stays False
        # and no code path contacts a real service.
        entry.status.confirmed = True
        entry.status.rejected = False
        entry.status.responder = responder
        entry.status.decided_at = datetime.now(UTC)
        return entry.status

    def reject(self, queue: QueueName, report_id: str, responder: str | None) -> DispatchStatus:
        """Record a rejection (or triage dismissal) and remove the item for good."""
        entry = self._require(queue, report_id)
        if entry.status.confirmed:
            raise DecisionConflict("report was already confirmed; it cannot be rejected")
        entry.status.rejected = True
        entry.status.responder = responder
        entry.status.decided_at = datetime.now(UTC)
        self._rejected.add((queue, report_id))
        del self._queues[queue][report_id]
        return entry.status

    def assign(self, report_id: str, service: Service, responder: str | None) -> list[QueueName]:
        """Send a triage item to a service queue. Returns every queue that changed.

        The service's responder still has to confirm the dispatch; this only gets the
        report in front of the right people.
        """
        entry = self._require(TRIAGE, report_id)
        report = entry.report
        who = responder or "a responder"
        report.route = report.route.model_copy(
            update={
                "services": {**report.route.services, service: 1.0},
                "needs_attention": False,
                "notes": [*report.route.notes, f"sent to {service} from triage by {who}"],
            }
        )
        entry.status.responder = responder
        entry.status.decided_at = datetime.now(UTC)
        self._rejected.add((TRIAGE, report_id))
        del self._queues[TRIAGE][report_id]
        return [TRIAGE, *self.apply_route(report)]

    def _require(self, queue: QueueName, report_id: str) -> QueueEntry:
        entry = self._queues[queue].get(report_id)
        if entry is None:
            raise KeyError(f"no queue entry for report {report_id} in {queue}")
        return entry
