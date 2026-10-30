/// frame_analyzer.dart - decides, frame by frame, whether the camera is looking at a steady,
/// sharp, well-lit document. The scanner keeps the camera open and captures automatically once
/// enough good frames in a row have been seen ("hold steady until the scan finishes").
///
/// It only reads the brightness (Y) plane of the live preview on a small sample grid, so it is
/// cheap. The thresholds are heuristics - tune them here if real-world testing says so.
library;

import 'dart:math' as math;

import 'package:camera/camera.dart';

class FrameReport {
  const FrameReport({
    required this.brightness,
    required this.sharpness,
    required this.motion,
    required this.contrast,
  });
  final double brightness; // 0..255
  final double sharpness; // mean gradient
  final double motion; // mean change vs the previous frame
  final double contrast; // std-dev of brightness

  bool get dark => brightness < Tuning.minBrightness;
  bool get glare => brightness > Tuning.maxBrightness;
  bool get noDocument => contrast < Tuning.minContrast;
  bool get moving => motion > Tuning.maxMotion;
  bool blurry(double best) => sharpness < Tuning.minSharpness || sharpness < best * Tuning.relativeSharpness;
}

class Tuning {
  static const minBrightness = 45.0;
  static const maxBrightness = 228.0;
  static const minContrast = 12.0; // a blank desk / wall has almost none
  static const maxMotion = 7.0; // average grey-level change between frames
  static const minSharpness = 3.0;
  static const relativeSharpness = 0.6; // must be >= 60% of the best sharpness seen so far
  static const goodFramesNeeded = 8; // ~1.3 s at ~6 frames per second
}

class FrameAnalyzer {
  List<int>? _prev;
  double bestSharpness = 0;

  void reset() {
    _prev = null;
    bestSharpness = 0;
  }

  FrameReport analyze(CameraImage image) {
    final plane = image.planes[0];
    final bytes = plane.bytes;
    final stride = plane.bytesPerRow;
    final w = image.width, h = image.height;

    // central 60% of the frame (the document is held in the middle of the screen)
    final x0 = (w * 0.2).round(), x1 = (w * 0.8).round() - 3;
    final y0 = (h * 0.2).round(), y1 = (h * 0.8).round() - 3;

    const gx = 40, gy = 30;
    double sum = 0, sumSq = 0, grad = 0;
    var n = 0;
    for (var j = 0; j < gy; j++) {
      final y = y0 + ((y1 - y0) * j) ~/ (gy - 1);
      for (var i = 0; i < gx; i++) {
        final x = x0 + ((x1 - x0) * i) ~/ (gx - 1);
        final v = bytes[y * stride + x];
        final vx = bytes[y * stride + x + 2];
        final vy = bytes[(y + 2) * stride + x];
        sum += v;
        sumSq += v * v;
        grad += (v - vx).abs() + (v - vy).abs();
        n++;
      }
    }
    final mean = sum / n;
    final variance = math.max(0.0, sumSq / n - mean * mean);
    final sharp = grad / (2 * n);

    // coarse 16x12 thumbnail to measure movement
    const tx = 16, ty = 12;
    final thumb = List<int>.filled(tx * ty, 0);
    for (var j = 0; j < ty; j++) {
      final y = y0 + ((y1 - y0) * j) ~/ (ty - 1);
      for (var i = 0; i < tx; i++) {
        final x = x0 + ((x1 - x0) * i) ~/ (tx - 1);
        thumb[j * tx + i] = bytes[y * stride + x];
      }
    }
    double motion = 99;
    final prev = _prev;
    if (prev != null) {
      var d = 0;
      for (var k = 0; k < thumb.length; k++) {
        d += (thumb[k] - prev[k]).abs();
      }
      motion = d / thumb.length;
    }
    _prev = thumb;
    bestSharpness = math.max(bestSharpness * 0.995, sharp);

    return FrameReport(brightness: mean, sharpness: sharp, motion: motion, contrast: math.sqrt(variance));
  }
}
