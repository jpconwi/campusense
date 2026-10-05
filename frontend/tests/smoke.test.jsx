// @vitest-environment jsdom
/*
 * Smoke test: renders the REAL React app in jsdom against a RUNNING backend
 * (uvicorn + PostgreSQL) and clicks through the main flows.
 *
 *   1) start the backend         (see README)
 *   2) COOKIES_FILE=/path/cookies.json npx vitest run
 *
 * COOKIES_FILE is a JSON file {"student": "<session cookie>", ...}; the README explains
 * how scripts/make_test_users.py makes it.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import fs from "node:fs";
import { MemoryRouter } from "react-router-dom";
import App from "../src/App.jsx";
import { AuthProvider } from "../src/auth.jsx";

const BASE = process.env.BACKEND || "http://localhost:8000";
const COOKIES = JSON.parse(fs.readFileSync(process.env.COOKIES_FILE || "/tmp/cookies.json", "utf8"));
const ADMIN_SECRET = process.env.ADMIN_LOGIN_SECRET || "mysecrets-dev";
const ADMIN_EMAIL = process.env.ADMIN_EMAIL || "admin@nemsu.edu.ph";
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || "long-enough-password";

let jar = "";
const errors = [];

beforeEach(() => {
  jar = "";
  errors.length = 0;
  // fetch with a tiny cookie jar, pointed at the live backend
  globalThis.fetch = async (url, opts = {}) => {
    const headers = { ...(opts.headers || {}), ...(jar ? { cookie: jar } : {}) };
    const response = await fetch_(BASE + url, { ...opts, headers });
    const set = response.headers.getSetCookie ? response.headers.getSetCookie() : [];
    for (const c of set) {
      const [pair] = c.split(";");
      const name = pair.split("=")[0];
      jar = jar.split("; ").filter((p) => p && !p.startsWith(name + "=")).concat(pair).join("; ");
    }
    return response;
  };
  window.open = () => null;
  Element.prototype.scrollIntoView = () => {};      // jsdom does not implement it (browsers do)
  const origError = console.error;
  console.error = (...a) => { errors.push(a.join(" ")); origError(...a); };
});
const fetch_ = globalThis.fetch;
afterEach(() => cleanup());

const signedInAs = (who) => { jar = `campusense_session=${COOKIES[who]}`; };

function open(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider><App /></AuthProvider>
    </MemoryRouter>
  );
}

describe("signed out", () => {
  it("shows the Google sign-in page", async () => {
    open("/ai");
    expect(await screen.findByText("Continue with Google")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Continue with Google/ })).toHaveAttribute("href", "/api/auth/google");
  });

  it("shows the reason when the server rejects an account", async () => {
    open("/login?error=wrong_account");
    expect(await screen.findByText("Please use your official NEMSU Google account.")).toBeInTheDocument();
  });

  it("a wrong admin secret looks like a normal 404", async () => {
    open("/admin/login/wrong-secret");
    expect(await screen.findByText("That page was not found.")).toBeInTheDocument();
    expect(screen.queryByText("Admin sign in")).toBeNull();
  });
});

describe("student", () => {
  it("chat -> prefilled concern form -> submit -> appears in My Concerns", async () => {
    const user = userEvent.setup();
    signedInAs("student");
    open("/ai");
    await screen.findByText("What do you need help with on campus?");
    expect(screen.queryByText("Faculty Availability")).toBeNull();           // student nav

    await user.type(screen.getByLabelText("Your question"), "The projector in Room 204 is broken.{Enter}");
    expect(await screen.findByText("Concern Form")).toBeInTheDocument();
    const room = screen.getByDisplayValue("Room 204");                        // prefilled by the AI intent
    expect(room).toBeInTheDocument();
    expect(screen.getByDisplayValue("Equipment")).toBeInTheDocument();

    // required fields are checked in the browser first
    await user.click(screen.getByRole("button", { name: "Submit" }));
    expect(await screen.findByText("Please complete all required fields.")).toBeInTheDocument();

    const labelled = (text) => screen.getByText(text, { selector: "label" }).nextElementSibling;
    await user.type(labelled("Location / Area *"), "CITE building");
    await user.click(screen.getByRole("button", { name: "Submit" }));
    expect(await screen.findByText(/Your concern has been submitted/)).toBeInTheDocument();
    expect(screen.getByText("Open PDF report")).toHaveAttribute("href", expect.stringMatching(/^\/api\/pdf\/concerns\/\d+$/));
  });

  it("asking about an instructor uses the database, not the model", async () => {
    const user = userEvent.setup();
    signedInAs("student");
    open("/ai");
    await screen.findByText("What do you need help with on campus?");
    await user.type(screen.getByLabelText("Your question"), "Is Sir Nobody available today?{Enter}");
    expect(await screen.findByText(/don't have an availability record for nobody/i)).toBeInTheDocument();
  });

  it("My Concerns lists the submission with its status", async () => {
    signedInAs("student");
    open("/concerns");
    expect(await screen.findByText("Your submissions")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("Pending").length).toBeGreaterThan(0));
    expect(screen.getAllByText("CITE building").length).toBeGreaterThan(0);
  });

  it("cannot open admin pages (looks like a 404) or the faculty page", async () => {
    signedInAs("student");
    open("/admin");
    expect(await screen.findByText("That page was not found.")).toBeInTheDocument();
    cleanup();
    open("/faculty");
    expect(await screen.findByText("Welcome, Sam")).toBeInTheDocument();      // sent back home
  });

  it("every normal page renders without errors", async () => {
    signedInAs("student");
    for (const [path, heading] of [["/", "Welcome, Sam"], ["/profile", "Profile"], ["/reports", "My Reports"],
                                   ["/feedback", "Feedback"], ["/reservations", "Reservations"]]) {
      open(path);
      expect(await screen.findByRole("heading", { level: 2, name: heading })).toBeInTheDocument();
      cleanup();
    }
    expect(errors).toEqual([]);
  });
});

describe("instructor", () => {
  it("'I cannot work today' opens the faculty form and the report is saved", async () => {
    const user = userEvent.setup();
    signedInAs("instructor");
    open("/ai");
    await screen.findByText("What do you need help with on campus?");
    await user.type(screen.getByLabelText("Your question"), "I cannot work today.{Enter}");
    expect(await screen.findByText("Faculty Availability Form")).toBeInTheDocument();
    const labelled = (text) => screen.getByText(text, { selector: "label" }).nextElementSibling;
    await user.type(labelled("Reason *"), "Fever");
    await user.type(labelled("Expected date to return *"), "2030-01-02");
    await user.click(screen.getByRole("button", { name: "Submit" }));
    expect(await screen.findByText(/faculty availability report has been submitted/)).toBeInTheDocument();
  });

  it("Faculty Availability page lists the report and 'I am back' works", async () => {
    const user = userEvent.setup();
    signedInAs("instructor");
    open("/faculty");
    expect((await screen.findAllByText("Fever")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Absent").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: /I am back/ }));
    await waitFor(() => expect(screen.queryAllByText("Absent")).toHaveLength(0));   // all my absences closed
    expect(screen.getAllByText("Available").length).toBeGreaterThan(0);
  });
});

describe("admin", () => {
  async function adminLogin(user) {
    open(`/admin/login/${ADMIN_SECRET}`);
    await user.type(await screen.findByLabelText("Email"), ADMIN_EMAIL);
    await user.type(screen.getByLabelText("Password"), "wrong-password-here");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Wrong email or password.")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Password"));
    await user.type(screen.getByLabelText("Password"), ADMIN_PASSWORD);
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Admin Dashboard")).toBeInTheDocument();
  }

  it("password login -> dashboard with real counts and charts", async () => {
    const user = userEvent.setup();
    await adminLogin(user);
    expect(screen.getByText("Pending Concerns")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Concerns by status" })).toBeInTheDocument();
    expect(document.querySelectorAll("svg.donut").length).toBe(3);
    expect(document.querySelector("svg.trend")).toBeTruthy();
    expect(screen.getByText("Dashboard", { selector: "a" })).toBeInTheDocument();
    expect(errors).toEqual([]);
  });

  it("changes a concern's status; the student then sees it", async () => {
    const user = userEvent.setup();
    await adminLogin(user);
    cleanup();
    open("/admin/concerns");
    expect(await screen.findByText("Student Concerns")).toBeInTheDocument();
    const row = (await screen.findAllByText("sam@nemsu.edu.ph"))[0].closest("tr");   // admins see who submitted it
    await user.selectOptions(within(row).getByLabelText("New status"), "Resolved");
    await user.click(within(row).getByRole("button", { name: "Save" }));
    expect(await screen.findByText(/changed to Resolved/)).toBeInTheDocument();

    cleanup();
    signedInAs("student");
    open("/concerns");
    expect((await screen.findAllByText("Resolved")).length).toBeGreaterThan(0);
  });

  it("admin pages all render", async () => {
    const user = userEvent.setup();
    await adminLogin(user);
    cleanup();
    for (const [path, heading] of [["/admin/users", "Users"], ["/admin/faculty", "Faculty Reports"],
                                   ["/admin/reports", "Campus Reports"], ["/admin/feedback", "Feedback"],
                                   ["/admin/reservations", "Reservations"], ["/admin/rooms", "Rooms"],
                                   ["/admin/campus", "Campus Information"]]) {
      open(path);
      expect(await screen.findByRole("heading", { level: 2, name: heading })).toBeInTheDocument();
      cleanup();
    }
    expect(errors).toEqual([]);
  });

  it("adds a room (the AI can then answer about it) and deletes it", async () => {
    const user = userEvent.setup();
    await adminLogin(user);
    cleanup();
    open("/admin/rooms");
    await screen.findByRole("heading", { level: 2, name: "Rooms" });
    const labelled = (text) => screen.getByText(text, { selector: "label" }).nextElementSibling;
    await user.type(labelled("Room ID *"), "204");
    await user.type(labelled("Name *"), "Room 204");
    await user.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByText("Room added.")).toBeInTheDocument();
    window.confirm = () => true;
    await user.click(await screen.findByRole("button", { name: "Delete" }));
    expect(await screen.findByText("Room deleted.")).toBeInTheDocument();
  });
});
