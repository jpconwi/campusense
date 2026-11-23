// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import "@testing-library/jest-dom/vitest";
import MapPinLink from "../src/components/MapPinLink.jsx";

afterEach(cleanup);

describe("MapPinLink", () => {
  it("opens the selected coordinates in Google Maps", () => {
    render(<MapPinLink latitude={9.078} longitude={126.198} />);

    const link = screen.getByRole("link", { name: "Open pin in Google Maps" });
    expect(link.getAttribute("href")).toBe(
      "https://www.google.com/maps/search/?api=1&query=9.078%2C126.198",
    );
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  });

  it("does not render a link for invalid coordinates", () => {
    render(<MapPinLink latitude="invalid" longitude={126.198} />);
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("does not render a link for out-of-range coordinates", () => {
    render(<MapPinLink latitude={91} longitude={126.198} />);
    expect(screen.queryByRole("link")).toBeNull();
  });
});
