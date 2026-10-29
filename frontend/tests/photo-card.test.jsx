// @vitest-environment jsdom
// Component tests for the photo report card and voice input (no backend needed).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";

vi.mock("../src/api.js", () => ({ api: vi.fn() }));
import { api } from "../src/api.js";

const result = (over = {}) => ({
  draft_id: 7, outcome: "issue", can_submit: true, message: "msg",
  questions: [{ key: "location", question: "Where on campus is this?" }, { key: "when", question: "When did you notice it?" }],
  analysis: { status: "analyzed", urgent: false, observations: ["Water stain on the ceiling"], issue_title: "Ceiling leak",
              confidence: "medium", check_explanation: "" },
  values: { description: "Leaking", location: "", noticed_when: "", observed_cause: "" }, checks_left: 5, ...over,
});

async function load() {
  vi.resetModules();
  return (await import("../src/components/PhotoReportCard.jsx")).default;
}

beforeEach(() => { api.mockReset(); delete window.SpeechRecognition; delete window.webkitSpeechRecognition; });
afterEach(cleanup);

describe("PhotoReportCard", () => {
  it("asks the follow-up questions, labels the AI notes as unverified and hides the mic without speech support", async () => {
    const Card = await load();
    render(<Card result={result()} onMessage={() => {}} onSent={() => {}} onDiscarded={() => {}} />);
    expect(screen.getByLabelText("Where on campus is this?")).toBeInTheDocument();
    expect(screen.getByLabelText("When did you notice it?")).toBeInTheDocument();
    expect(screen.getByText(/AI guess, not verified/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Speak your message/)).toBeNull();
  });

  it("shows a hazard warning", async () => {
    const Card = await load();
    const r = result(); r.analysis.urgent = true;
    render(<Card result={r} onMessage={() => {}} onSent={() => {}} onDiscarded={() => {}} />);
    expect(screen.getByText(/Possible safety hazard/)).toBeInTheDocument();
  });

  it("cannot be sent when the report is not plausible, and 'Check again' needs an edit", async () => {
    const Card = await load();
    render(<Card result={result({ can_submit: false, outcome: "no_issue", questions: [] })} onMessage={() => {}} onSent={() => {}} onDiscarded={() => {}} />);
    expect(screen.getByRole("button", { name: "Send report" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Check again" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Your description"), " more");
    expect(screen.getByRole("button", { name: "Check again" })).toBeEnabled();
  });

  it("re-checks with the edited text and shows the new message", async () => {
    const Card = await load();
    const onMessage = vi.fn();
    api.mockResolvedValue(result({ message: "second look", questions: [], values: { description: "Leaking more", location: "", noticed_when: "", observed_cause: "" } }));
    render(<Card result={result()} onMessage={onMessage} onSent={() => {}} onDiscarded={() => {}} />);
    await userEvent.type(screen.getByLabelText("Your description"), " more");
    await userEvent.click(screen.getByRole("button", { name: "Check again" }));
    await waitFor(() => expect(onMessage).toHaveBeenCalledWith("second look"));
    const [path, opts] = api.mock.calls[0];
    expect(path).toBe("/api/reports/photo/analyze");
    expect(opts.form.get("draft_id")).toBe("7");
    expect(opts.form.get("description")).toBe("Leaking more");
  });

  it("sends the report and reports success", async () => {
    const Card = await load();
    const onSent = vi.fn();
    api.mockResolvedValue({ success: true, id: 12, status: "Pending", message: "sent" });
    render(<Card result={result()} onMessage={() => {}} onSent={onSent} onDiscarded={() => {}} />);
    await userEvent.type(screen.getByLabelText("Where on campus is this?"), "Library");
    await userEvent.click(screen.getByRole("button", { name: "Send report" }));
    await waitFor(() => expect(onSent).toHaveBeenCalled());
    expect(api.mock.calls[0][0]).toBe("/api/reports/photo/7/submit");
    expect(api.mock.calls[0][1].form.get("location")).toBe("Library");
    expect(screen.getByText("Report sent.")).toBeInTheDocument();
  });

  it("shows the server's error and stays open", async () => {
    const Card = await load();
    api.mockRejectedValue(new Error("I can't send this yet."));
    render(<Card result={result()} onMessage={() => {}} onSent={() => {}} onDiscarded={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: "Send report" }));
    expect(await screen.findByText("I can't send this yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send report" })).toBeEnabled();
  });

  it("discard removes the photo", async () => {
    const Card = await load();
    const onDiscarded = vi.fn();
    api.mockResolvedValue({ success: true });
    render(<Card result={result()} onMessage={() => {}} onSent={() => {}} onDiscarded={onDiscarded} />);
    await userEvent.click(screen.getByRole("button", { name: "Discard photo" }));
    await waitFor(() => expect(onDiscarded).toHaveBeenCalled());
    expect(api.mock.calls[0][1].method).toBe("DELETE");
  });
});

describe("voice input", () => {
  it("puts spoken words into the editable box, and the student can fix them", async () => {
    let instance;
    window.webkitSpeechRecognition = class {
      constructor() { instance = this; }
      start() {} stop() { this.onend && this.onend(); } abort() {}
    };
    const Card = await load();
    render(<Card result={result({ values: { description: "", location: "", noticed_when: "", observed_cause: "" } })}
                 onMessage={() => {}} onSent={() => {}} onDiscarded={() => {}} />);
    const mics = screen.getAllByRole("button", { name: "Speak your message" });
    await userEvent.click(mics[0]);
    expect(instance.lang).toBe("en-PH");
    instance.onresult({ results: [[{ transcript: "the roof is leakng" }]] });
    const box = screen.getByLabelText("Your description");
    await waitFor(() => expect(box).toHaveValue("the roof is leakng"));
    await userEvent.click(screen.getByRole("button", { name: "Stop voice input" }));
    await userEvent.clear(box);
    await userEvent.type(box, "the roof is leaking");
    expect(box).toHaveValue("the roof is leaking");
  });

  it("explains a blocked microphone", async () => {
    let instance;
    window.webkitSpeechRecognition = class { constructor() { instance = this; } start() {} stop() {} abort() {} };
    const Card = await load();
    render(<Card result={result()} onMessage={() => {}} onSent={() => {}} onDiscarded={() => {}} />);
    await userEvent.click(screen.getAllByRole("button", { name: "Speak your message" })[0]);
    instance.onerror({ error: "not-allowed" });
    expect(await screen.findByText(/Microphone access is blocked/)).toBeInTheDocument();
  });
});
