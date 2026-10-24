"""Unit tests for the dispatch queues and human-confirmation rules."""

from __future__ import annotations

import pytest

from app.dispatch.queues import REAL_DISPATCH_ENABLED, DecisionConflict, DispatchHub
from app.domain.models import Report, RouteDecision, Service


def _report(report_id: str = "r1", **services: float) -> Report:
    route = RouteDecision(services=dict(services))  # type: ignore[arg-type]
    return Report(id=report_id, route=route)


def _ids(hub: DispatchHub, service: Service) -> list[str]:
    return [e["report_id"] for e in hub.snapshot(service)]


def test_real_dispatch_guard_is_off() -> None:
    assert REAL_DISPATCH_ENABLED is False


def test_route_fans_out_to_each_service() -> None:
    hub = DispatchHub()
    touched = hub.apply_route(_report(police=0.6, fire=0.5))
    assert set(touched) == {"police", "fire"}
    assert _ids(hub, "police") == ["r1"]
    assert _ids(hub, "fire") == ["r1"]
    assert _ids(hub, "medical") == []


def test_undecided_entry_is_removed_when_route_no_longer_includes_it() -> None:
    hub = DispatchHub()
    report = _report(police=0.6, medical=0.5)
    hub.apply_route(report)
    report.route = RouteDecision(services={"police": 0.6})
    hub.apply_route(report)
    assert _ids(hub, "medical") == []
    assert _ids(hub, "police") == ["r1"]


def test_confirmed_entry_survives_a_later_route_change() -> None:
    hub = DispatchHub()
    report = _report(medical=0.6)
    hub.apply_route(report)
    hub.confirm("medical", "r1", "disp")
    report.route = RouteDecision(services={})
    hub.apply_route(report)
    assert _ids(hub, "medical") == ["r1"]


def test_rejected_report_does_not_come_back_on_the_next_update() -> None:
    hub = DispatchHub()
    report = _report(police=0.6)
    hub.apply_route(report)
    hub.reject("police", "r1", "disp")
    assert _ids(hub, "police") == []

    report.route = RouteDecision(services={"police": 0.9})
    assert hub.apply_route(report) == []
    assert _ids(hub, "police") == []


def test_rejecting_one_service_leaves_the_others() -> None:
    hub = DispatchHub()
    report = _report(police=0.6, fire=0.6)
    hub.apply_route(report)
    hub.reject("police", "r1", "disp")
    hub.apply_route(report)
    assert _ids(hub, "fire") == ["r1"]


def test_confirm_records_who_and_when() -> None:
    hub = DispatchHub()
    hub.apply_route(_report(fire=0.8))
    status = hub.confirm("fire", "r1", "disp-1")
    assert status.confirmed and not status.rejected
    assert status.responder == "disp-1"
    assert status.decided_at is not None


def test_cannot_reject_after_confirming() -> None:
    hub = DispatchHub()
    hub.apply_route(_report(fire=0.8))
    hub.confirm("fire", "r1", "disp-1")
    with pytest.raises(DecisionConflict):
        hub.reject("fire", "r1", "disp-2")


def test_decisions_on_unknown_entries_raise() -> None:
    hub = DispatchHub()
    with pytest.raises(KeyError):
        hub.confirm("fire", "nope", None)
    with pytest.raises(KeyError):
        hub.reject("fire", "nope", None)


def test_forget_clears_entries_and_rejections() -> None:
    hub = DispatchHub()
    report = _report(police=0.6, fire=0.6)
    hub.apply_route(report)
    hub.reject("police", "r1", None)
    hub.forget("r1")
    assert _ids(hub, "fire") == []
    assert hub.apply_route(report) == ["police", "fire"]


# --- triage: reports the system could not classify ---------------------------


def test_an_unclassified_report_goes_to_triage_not_nowhere() -> None:
    hub = DispatchHub()
    touched = hub.apply_route(_report())  # nothing routed
    assert touched == ["triage"]
    assert _ids(hub, "triage") == ["r1"]
    assert all(_ids(hub, s) == [] for s in ("police", "fire", "medical"))


def test_a_classified_report_never_appears_in_triage() -> None:
    hub = DispatchHub()
    hub.apply_route(_report(fire=0.8))
    assert _ids(hub, "triage") == []


def test_triage_entry_moves_out_when_the_system_later_classifies_the_report() -> None:
    hub = DispatchHub()
    report = _report()
    hub.apply_route(report)
    assert _ids(hub, "triage") == ["r1"]

    report.route = RouteDecision(services={"fire": 0.7})
    touched = hub.apply_route(report)
    assert set(touched) == {"triage", "fire"}
    assert _ids(hub, "triage") == []
    assert _ids(hub, "fire") == ["r1"]


def test_assign_sends_a_triage_item_to_a_service_with_a_note() -> None:
    hub = DispatchHub()
    report = _report()
    hub.apply_route(report)
    touched = hub.assign("r1", "medical", "disp-9")
    assert set(touched) == {"triage", "medical"}
    assert _ids(hub, "triage") == []
    assert _ids(hub, "medical") == ["r1"]
    entry = hub.snapshot("medical")[0]
    assert any("sent to medical from triage by disp-9" in n for n in entry["notes"])
    assert entry["needs_attention"] is False
    # Assigning is not dispatching: the service's responder must still confirm.
    assert entry["dispatch"]["confirmed"] is False


def test_assigned_item_does_not_bounce_back_to_triage() -> None:
    hub = DispatchHub()
    report = _report()
    hub.apply_route(report)
    hub.assign("r1", "police", None)
    hub.apply_route(report)
    assert _ids(hub, "triage") == []


def test_dismissing_a_triage_item_is_permanent() -> None:
    hub = DispatchHub()
    report = _report()
    hub.apply_route(report)
    hub.reject("triage", "r1", "disp")
    hub.apply_route(report)
    assert _ids(hub, "triage") == []


def test_triage_items_cannot_be_confirmed_as_a_dispatch() -> None:
    hub = DispatchHub()
    hub.apply_route(_report())
    with pytest.raises(DecisionConflict):
        hub.confirm("triage", "r1", "disp")


def test_assigning_something_not_in_triage_raises() -> None:
    hub = DispatchHub()
    with pytest.raises(KeyError):
        hub.assign("nope", "fire", None)
