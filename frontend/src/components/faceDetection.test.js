import { describe, expect, it } from "vitest";
import { hasSelfieSizedFace } from "./faceDetection.js";

describe("hasSelfieSizedFace", () => {
  it("rejects a face filling the scan area", () => {
    expect(hasSelfieSizedFace([{
      categories: [{ score: 0.9 }],
      boundingBox: { originX: 280, originY: 100, width: 440, height: 600 },
    }], { left: 0, top: 0, width: 1000, height: 1000 })).toBe(true);
  });

  it("allows a smaller portrait within an ID", () => {
    expect(hasSelfieSizedFace([{
      categories: [{ score: 0.9 }],
      boundingBox: { originX: 70, originY: 80, width: 230, height: 300 },
    }], { left: 0, top: 0, width: 1000, height: 1000 })).toBe(false);
  });
});
