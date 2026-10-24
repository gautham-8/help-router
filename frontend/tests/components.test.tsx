import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { HeardPanel } from "../src/caller/HeardPanel";
import { RouteSummary } from "../src/caller/RouteSummary";
import { QueueColumn } from "../src/dashboard/QueueColumn";
import type { QueueEntryView } from "../src/lib/types";

function entry(overrides: Partial<QueueEntryView> = {}): QueueEntryView {
  return {
    report_id: "abc123",
    service: "fire",
    confidence: 0.82,
    route_status: "provisional",
    needs_attention: false,
    notes: [],
    transcript: "help there's smoke in the kitchen",
    events: [{ kind: "smoke_alarm", confidence: 0.95 }],
    location: { lat: 42.36, lon: -71.06, accuracy_m: 10, known: true },
    dispatch: {
      report_id: "abc123",
      service: "fire",
      confirmed: false,
      rejected: false,
      responder: null,
      decided_at: null,
    },
    created_at: "2026-10-24T12:00:00Z",
    ...overrides,
  };
}

describe("QueueColumn", () => {
  it("shows the evidence a responder needs to decide", () => {
    render(<QueueColumn service="fire" entries={[entry()]} onConfirm={vi.fn()} onReject={vi.fn()} />);
    expect(screen.getByText("82% confidence")).toBeTruthy();
    expect(screen.getByText("provisional")).toBeTruthy();
    expect(screen.getByText(/smoke in the kitchen/)).toBeTruthy();
    expect(screen.getByText(/smoke alarm \(95%\)/)).toBeTruthy();
    expect(screen.getByText(/42\.3600, -71\.0600/)).toBeTruthy();
  });

  it("says so when the location is unknown", () => {
    const unknown = entry({ location: { lat: null, lon: null, accuracy_m: null, known: false } });
    render(<QueueColumn service="fire" entries={[unknown]} onConfirm={vi.fn()} onReject={vi.fn()} />);
    expect(screen.getByText(/location unknown/)).toBeTruthy();
  });

  it("only dispatches through an explicit human click", () => {
    const onConfirm = vi.fn();
    const onReject = vi.fn();
    render(<QueueColumn service="fire" entries={[entry()]} onConfirm={onConfirm} onReject={onReject} />);
    expect(onConfirm).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Confirm dispatch" }));
    expect(onConfirm).toHaveBeenCalledWith("fire", "abc123");

    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(onReject).toHaveBeenCalledWith("fire", "abc123");
  });

  it("replaces the buttons once a responder has confirmed", () => {
    const confirmed = entry({
      dispatch: { ...entry().dispatch, confirmed: true, responder: "disp-1" },
    });
    render(<QueueColumn service="fire" entries={[confirmed]} onConfirm={vi.fn()} onReject={vi.fn()} />);
    expect(screen.getByText(/confirmed by disp-1/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Confirm dispatch" })).toBeNull();
  });

  it("collapses repeated sound readings to the strongest one per kind", () => {
    const noisy = entry({
      events: [
        { kind: "siren", confidence: 0.3 },
        { kind: "smoke_alarm", confidence: 0.95 },
        { kind: "siren", confidence: 0.6 },
        { kind: "siren", confidence: 0.4 },
      ],
    });
    render(<QueueColumn service="fire" entries={[noisy]} onConfirm={vi.fn()} onReject={vi.fn()} />);
    expect(screen.getAllByText(/siren/)).toHaveLength(1);
    expect(screen.getByText(/siren \(60%\)/)).toBeTruthy();
    expect(screen.getByText(/smoke alarm \(95%\)/)).toBeTruthy();
  });

  it("shows an empty state", () => {
    render(<QueueColumn service="police" entries={[]} onConfirm={vi.fn()} onReject={vi.fn()} />);
    expect(screen.getByText("No active reports.")).toBeTruthy();
  });
});

describe("QueueColumn (triage)", () => {
  const triageEntry = () =>
    entry({
      service: "triage",
      confidence: 0,
      needs_attention: true,
      transcript: "",
      events: [],
      missing_signals: ["transcript"],
      dispatch: { ...entry().dispatch, service: "triage" },
    });

  it("explains itself and lists what the caller's device could not provide", () => {
    render(<QueueColumn service="triage" entries={[triageEntry()]} onConfirm={vi.fn()} onReject={vi.fn()} />);
    expect(screen.getByRole("region", { name: "Needs triage queue" })).toBeTruthy();
    expect(screen.getByText(/could not tell which service/)).toBeTruthy();
    expect(screen.getByText(/no speech transcript/)).toBeTruthy();
  });

  it("lets a human send the report to each service, or dismiss it, and never 'confirm'", () => {
    const onAssign = vi.fn();
    const onReject = vi.fn();
    render(
      <QueueColumn
        service="triage"
        entries={[triageEntry()]}
        onConfirm={vi.fn()}
        onReject={onReject}
        onAssign={onAssign}
      />,
    );
    expect(screen.queryByRole("button", { name: "Confirm dispatch" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Send to Police" }));
    fireEvent.click(screen.getByRole("button", { name: "Send to Fire" }));
    fireEvent.click(screen.getByRole("button", { name: "Send to Medical" }));
    expect(onAssign.mock.calls).toEqual([
      ["abc123", "police"],
      ["abc123", "fire"],
      ["abc123", "medical"],
    ]);

    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onReject).toHaveBeenCalledWith("triage", "abc123");
  });

  it("does not show a made-up confidence for an unclassified report", () => {
    render(<QueueColumn service="triage" entries={[triageEntry()]} onConfirm={vi.fn()} onReject={vi.fn()} />);
    expect(screen.queryByText(/% confidence/)).toBeNull();
  });
});

describe("HeardPanel", () => {
  it("shows nothing before the first chunk", () => {
    const { container } = render(<HeardPanel chunks={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows what was heard, and says plainly when a signal was unavailable", () => {
    render(
      <HeardPanel
        chunks={[
          { index: 0, text: "help there is smoke", events: [{ kind: "smoke_alarm", confidence: 0.84 }] },
          { index: 1, text: null, events: [] },
          { index: 2, text: "", events: null },
        ]}
      />,
    );
    expect(screen.getByText(/help there is smoke/)).toBeTruthy();
    expect(screen.getByText(/smoke alarm 84%/)).toBeTruthy();
    expect(screen.getByText(/speech unavailable · no notable sounds/)).toBeTruthy();
    expect(screen.getByText(/… · sounds unavailable/)).toBeTruthy();
  });
});

describe("RouteSummary", () => {
  it("labels provisional vs refined routes and lists services in order", () => {
    const { rerender, container } = render(
      <RouteSummary
        decision={{ services: { medical: 0.5, police: 0.9 }, status: "provisional", needs_attention: false, notes: [] }}
      />,
    );
    expect(screen.getByText("Provisional route")).toBeTruthy();
    expect(Array.from(container.querySelectorAll(".pill")).map((n) => n.textContent)).toEqual([
      "Police",
      "Medical",
    ]);

    rerender(
      <RouteSummary
        decision={{ services: { police: 0.9 }, status: "refined", needs_attention: false, notes: [] }}
      />,
    );
    expect(screen.getByText("Refined route")).toBeTruthy();
  });

  it("flags a route with no clear service", () => {
    render(
      <RouteSummary decision={{ services: {}, status: "provisional", needs_attention: true, notes: [] }} />,
    );
    expect(screen.getByText(/flagged for a responder/)).toBeTruthy();
  });
});
