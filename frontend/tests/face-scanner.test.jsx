// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "@testing-library/jest-dom/vitest";
import FaceScanner from "../src/components/FaceScanner.jsx";
import { api } from "../src/api.js";

vi.mock("../src/api.js", () => ({ api: vi.fn() }));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("captures automatically after the face guide stays green", async () => {
  const user = userEvent.setup();
  const track = { stop: vi.fn() };
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track] }) },
  });
  vi.spyOn(HTMLVideoElement.prototype, "play").mockResolvedValue();
  Object.defineProperty(HTMLVideoElement.prototype, "videoWidth", { configurable: true, get: () => 640 });
  Object.defineProperty(HTMLVideoElement.prototype, "videoHeight", { configurable: true, get: () => 480 });
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ drawImage: vi.fn() });
  vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation((callback) => {
    callback(new Blob(["selfie"], { type: "image/jpeg" }));
  });
  vi.mocked(api).mockResolvedValue({ ready: true, available: true });

  render(<FaceScanner onComplete={vi.fn()} />);
  await user.click(screen.getByRole("button", { name: "Start face scan" }));
  expect(await screen.findByText("Face is centered. Hold still—the selfie will capture when the guide stays green."))
    .toBeInTheDocument();
  expect(await screen.findByText("Selfie captured. Continue with registration.")).toBeInTheDocument();
  expect(api).toHaveBeenCalledTimes(2);
});
