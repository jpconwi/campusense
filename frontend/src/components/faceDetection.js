import { FaceDetector, FilesetResolver } from "@mediapipe/tasks-vision";

const detectorPromises = new Map();

export function getFaceDetector(runningMode) {
  if (!detectorPromises.has(runningMode)) {
    const detector = FilesetResolver.forVisionTasks(
      "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.2.3/wasm",
    ).then((vision) => FaceDetector.createFromOptions(vision, {
      baseOptions: { modelAssetPath: "/models/blaze_face_short_range.tflite" },
      runningMode,
      minDetectionConfidence: 0.55,
    })).catch((error) => {
      detectorPromises.delete(runningMode);
      throw error;
    });
    detectorPromises.set(runningMode, detector);
  }
  return detectorPromises.get(runningMode);
}

export function hasSelfieSizedFace(detections, frame) {
  return detections.some(({ categories, boundingBox }) => {
    if ((categories?.[0]?.score ?? 0) < 0.55 || !boundingBox) return false;
    const left = Math.max(frame.left, boundingBox.originX);
    const top = Math.max(frame.top, boundingBox.originY);
    const right = Math.min(frame.left + frame.width, boundingBox.originX + boundingBox.width);
    const bottom = Math.min(frame.top + frame.height, boundingBox.originY + boundingBox.height);
    const widthRatio = Math.max(0, right - left) / frame.width;
    const heightRatio = Math.max(0, bottom - top) / frame.height;
    // Catch close-up selfies while still allowing the small portrait printed
    // on an ID card (usually short in relation to the full document frame).
    return widthRatio >= 0.2 && heightRatio >= 0.32 && widthRatio * heightRatio >= 0.08;
  });
}

export function hasVisibleFace(detections, frame) {
  return detections.some(({ categories, boundingBox }) => {
    if ((categories?.[0]?.score ?? 0) < 0.55 || !boundingBox) return false;
    const left = Math.max(frame.left, boundingBox.originX);
    const top = Math.max(frame.top, boundingBox.originY);
    const right = Math.min(frame.left + frame.width, boundingBox.originX + boundingBox.width);
    const bottom = Math.min(frame.top + frame.height, boundingBox.originY + boundingBox.height);
    const widthRatio = Math.max(0, right - left) / frame.width;
    const heightRatio = Math.max(0, bottom - top) / frame.height;
    return widthRatio >= 0.05 && heightRatio >= 0.08;
  });
}
