// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { MemoryRouter } from "react-router-dom";
import App from "../src/App.jsx";

vi.mock("../src/auth.jsx", () => ({
  useAuth: () => ({ loading: false, user: null }),
}));

afterEach(() => cleanup());

function open(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>
  );
}

describe("public information pages", () => {
  it("shows a public app overview with links to both policies", () => {
    open("/about");

    expect(screen.getAllByRole("heading", { name: "NEMSAI" })).not.toHaveLength(0);
    expect(screen.getAllByRole("link", { name: "Privacy Policy" }).some(
      (link) => link.getAttribute("href") === "/privacy-policy"
    )).toBe(true);
    expect(screen.getAllByRole("link", { name: "Terms of Service" }).some(
      (link) => link.getAttribute("href") === "/terms-of-service"
    )).toBe(true);
  });

  it("shows the privacy disclosures without requiring sign-in", () => {
    open("/privacy-policy");

    expect(screen.getByRole("heading", { name: "Privacy Policy" })).toBeInTheDocument();
    expect(screen.getByText(/does not access your Gmail inbox/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "jpconwi2005@gmail.com" })).toHaveAttribute(
      "href",
      "mailto:jpconwi2005@gmail.com"
    );
  });

  it("shows the terms of service without requiring sign-in", () => {
    open("/terms-of-service");

    expect(screen.getByRole("heading", { name: "Terms of Service" })).toBeInTheDocument();
    expect(screen.getByText(/AI-generated information may be incomplete or inaccurate/i)).toBeInTheDocument();
  });
});
