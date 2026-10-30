/// image_tools.dart - crop / shrink / quality-check photos. Heavy work runs in a background
/// isolate through compute(), so the camera screen never freezes.
library;

import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:image/image.dart' as img;

import '../api/api_client.dart';

/// Can this phone list at least one camera? (A broken / missing camera -> upload only.)
class CameraProbe {
  static Future<bool>? _result;
  static Future<bool> available() => _result ??= _probe();
  static void reset() => _result = null;

  static Future<bool> _probe() async {
    try {
      return (await availableCameras()).isNotEmpty;
    } catch (_) {
      return false;
    }
  }
}

/// Which format the bytes really are ("jpg", "png", "webp") or null. Same magic-byte test the
/// server uses, so a renamed file cannot slip through.
String? sniffImage(String path) {
  try {
    final raf = File(path).openSync();
    final head = raf.readSync(12);
    raf.closeSync();
    if (head.length >= 3 && head[0] == 0xFF && head[1] == 0xD8 && head[2] == 0xFF) return 'jpg';
    if (head.length >= 8 &&
        head[0] == 0x89 && head[1] == 0x50 && head[2] == 0x4E && head[3] == 0x47) {
      return 'png';
    }
    if (head.length >= 12 &&
        String.fromCharCodes(head.sublist(0, 4)) == 'RIFF' &&
        String.fromCharCodes(head.sublist(8, 12)) == 'WEBP') {
      return 'webp';
    }
  } catch (_) {}
  return null;
}

UploadFile toUpload(File file, String baseName) =>
    UploadFile(file.path, filename: '$baseName.${sniffImage(file.path) ?? 'jpg'}');

// ------------------------------------------------------------------ isolate jobs
/// args: src, dst, u0, v0, u1, v1 (normalised 0..1 crop), maxSide
String _cropJob(Map<String, Object?> a) {
  final bytes = File(a['src']! as String).readAsBytesSync();
  var image = img.decodeImage(bytes);
  if (image == null) throw const FormatException('decode failed');
  image = img.bakeOrientation(image);

  final u0 = (a['u0']! as double).clamp(0.0, 1.0);
  final v0 = (a['v0']! as double).clamp(0.0, 1.0);
  final u1 = (a['u1']! as double).clamp(0.0, 1.0);
  final v1 = (a['v1']! as double).clamp(0.0, 1.0);

  final x = (u0 * image.width).round().clamp(0, image.width - 1).toInt();
  final y = (v0 * image.height).round().clamp(0, image.height - 1).toInt();
  final w = ((u1 - u0) * image.width).round().clamp(1, image.width - x).toInt();
  final h = ((v1 - v0) * image.height).round().clamp(1, image.height - y).toInt();

  var out = img.copyCrop(image, x: x, y: y, width: w, height: h);
  final maxSide = a['maxSide']! as int;
  if (math.max(out.width, out.height) > maxSide) {
    out = out.width >= out.height
        ? img.copyResize(out, width: maxSide)
        : img.copyResize(out, height: maxSide);
  }
  File(a['dst']! as String).writeAsBytesSync(img.encodeJpg(out, quality: 90));
  return a['dst']! as String;
}

Future<String> cropToFile({
  required String src,
  required String dst,
  required double u0,
  required double v0,
  required double u1,
  required double v1,
  int maxSide = 1800,
}) =>
    compute(_cropJob, <String, Object?>{
      'src': src, 'dst': dst, 'u0': u0, 'v0': v0, 'u1': u1, 'v1': v1, 'maxSide': maxSide,
    });

/// Re-encode as a smaller JPEG (used when a chosen photo is over the 5 MB limit).
String _shrinkJob(Map<String, Object?> a) {
  final bytes = File(a['src']! as String).readAsBytesSync();
  var image = img.decodeImage(bytes);
  if (image == null) throw const FormatException('decode failed');
  image = img.bakeOrientation(image);
  const maxSide = 2200;
  if (math.max(image.width, image.height) > maxSide) {
    image = image.width >= image.height
        ? img.copyResize(image, width: maxSide)
        : img.copyResize(image, height: maxSide);
  }
  File(a['dst']! as String).writeAsBytesSync(img.encodeJpg(image, quality: 85));
  return a['dst']! as String;
}

Future<String> shrinkToJpeg(String src, String dst) =>
    compute(_shrinkJob, <String, Object?>{'src': src, 'dst': dst});

/// Rough quality check on a small grayscale copy: too dark, glare, blur (Laplacian variance).
/// Same thresholds as the website's scanner.
List<String> _qualityJob(String path) {
  try {
    var image = img.decodeImage(File(path).readAsBytesSync());
    if (image == null) return const [];
    image = img.bakeOrientation(image);
    const w = 240;
    final h = math.max(1, (image.height / image.width * w).round());
    final s = img.copyResize(image, width: w, height: h);

    final g = Float32List(w * h);
    double sum = 0;
    for (var y = 0; y < h; y++) {
      for (var x = 0; x < w; x++) {
        final p = s.getPixel(x, y);
        final v = 0.299 * p.r + 0.587 * p.g + 0.114 * p.b;
        g[y * w + x] = v;
        sum += v;
      }
    }
    final mean = sum / (w * h);
    double acc = 0;
    int n = 0;
    for (var y = 1; y < h - 1; y++) {
      for (var x = 1; x < w - 1; x++) {
        final i = y * w + x;
        final lap = g[i - 1] + g[i + 1] + g[i - w] + g[i + w] - 4 * g[i];
        acc += lap * lap;
        n++;
      }
    }
    final sharp = n > 0 ? acc / n : 0;
    final warns = <String>[];
    if (mean < 45) {
      warns.add('The photo looks dark. Move to a brighter place.');
    } else if (mean > 232) {
      warns.add('There may be glare. Tilt the card slightly and retake.');
    }
    if (sharp < 18) {
      warns.add('The text may be blurry. Hold steady and retake if you cannot read it.');
    }
    return warns;
  } catch (_) {
    return const [];
  }
}

Future<List<String>> checkQuality(String path) => compute(_qualityJob, path);
