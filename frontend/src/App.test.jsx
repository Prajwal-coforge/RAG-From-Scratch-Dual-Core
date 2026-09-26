import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App.jsx";

function mockFetch(handler) {
  global.fetch = vi.fn(async (url, options) => handler(url, options));
}

beforeEach(() => {
  mockFetch(async (url) => {
    if (url === "/api/corpora") {
      return json({
        corpora: [
          { corpus_id: "airport-generated", snapshot_id: "clean", issuer: "AeroPolicy Airport" },
          { corpus_id: "skywings-baggage", snapshot_id: "imported:skywings-baggage", issuer: "SkyWings Airlines" },
        ],
      });
    }
    return json({ detail: "unused" }, 404);
  });
});

function json(body, status = 200) {
  return { ok: status < 400, status, json: async () => body };
}

test("a citation opens the original excerpt, version, and section", async () => {
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole("heading", { name: "Airport Policy Assistant" });
  expect(screen.queryByLabelText("As of (optional)")).not.toBeInTheDocument();
  await user.type(screen.getByLabelText("Question"), "Who escalates a leaking bag?");
  global.fetch = vi.fn(async (url) => {
    if (url === "/api/corpora") return json({ corpora: [] });
    return json({
      triage: { status: "routed" },
      trace: null,
      answer: {
        status: "answered",
        answer: "Escalate within 10 minutes [1].",
        follow_up_questions: [],
        citations: [
          {
            citation_id: 1,
            document_title: "AP-BAG-001 v2 Staff Baggage",
            version: "2",
            section_path: "4 Escalation",
            excerpt: "Escalate within 10 minutes to the Baggage Duty Supervisor.",
            resolved: true,
          },
        ],
      },
    });
  });
  await user.click(screen.getByRole("button", { name: "Ask" }));
  await user.click(screen.getByRole("button", { name: /AP-BAG-001 v2/ }));
  expect(screen.getByRole("dialog")).toHaveTextContent("Escalate within 10 minutes to the Baggage Duty Supervisor.");
  expect(screen.getByRole("dialog")).toHaveTextContent("Version 2");
  expect(screen.getByRole("dialog")).toHaveTextContent("Section 4 Escalation");
});

test("a down service shows unavailable and no fabricated answer", async () => {
  const user = userEvent.setup();
  render(<App />);
  await screen.findByLabelText("Question");
  await user.type(screen.getByLabelText("Question"), "Who escalates a leaking bag?");
  global.fetch = vi.fn(async () => {
    throw new Error("network down");
  });
  await user.click(screen.getByRole("button", { name: "Ask" }));
  expect(screen.getByText("Unavailable")).toBeInTheDocument();
  expect(screen.getByText("The answer service is unavailable.")).toBeInTheDocument();
  expect(screen.queryByText(/10 minutes/)).not.toBeInTheDocument();
});

test("ask does not send a policy context and still shows a follow-up", async () => {
  const user = userEvent.setup();
  render(<App />);
  await screen.findByLabelText("Question");
  expect(screen.queryByLabelText("Policy context")).not.toBeInTheDocument();
  await user.type(screen.getByLabelText("Question"), "What is the checked bag weight?");
  let sent = null;
  global.fetch = vi.fn(async (url, options) => {
    sent = JSON.parse(options?.body || "{}");
    return json({
      triage: { status: "routed", route: "model" },
      trace: null,
      answer: {
        status: "needs_clarification",
        answer: "More information is needed: the rule depends on travel class.",
        follow_up_questions: ["Which travel class is the passenger flying: Economy, Business, or First Class?"],
        citations: [],
      },
    });
  });
  await user.click(screen.getByRole("button", { name: "Ask" }));
  expect(sent.corpus_id).toBeNull();
  expect(screen.getByText("Needs clarification")).toBeInTheDocument();
  expect(screen.getByText(/Which travel class/)).toBeInTheDocument();
  expect(screen.queryByText(/Which policy context/)).not.toBeInTheDocument();
});
