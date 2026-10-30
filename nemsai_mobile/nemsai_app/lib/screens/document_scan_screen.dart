/// document_scan_screen.dart - full-screen built-in camera for scanning a school ID (front/back) or a COR.
///
/// The camera stays open with a frame on screen. The person fits the document inside the frame and
/// holds still; the app watches the live preview and, once it has seen a steady, sharp, well-lit
/// document for about a second, it captures, crops to the frame and finishes by itself. A manual
/// shutter is always available as a fallback, plus a torch toggle for dim rooms.
///
/// Result (via Navigator.pop): a [ScanResult] with the cropped JPEG, or an error text when the
/// camera could not be used (so the caller can fall back to "Upload").
library;

import 'dart:async';
import 'dart:io';
import 'dart:math' as math;

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';

import '../theme.dart';
import '../util/frame_analyzer.dart';
import '../util/image_tools.dart';

enum ScanKind { idFront, idBack, cor }

class ScanSpec {
  const ScanSpec(this.title, this.short, this.ratio, this.hint, this.baseName);
  final String title;
  final String short;
  final double ratio; // width / height of the document frame
  final String hint;
  final String baseName;
}

const scanSpecs = <ScanKind, ScanSpec>{
  ScanKind.idFront: ScanSpec('School ID - front', 'ID SCAN', 1.586, 'Fit the front of your ID inside the frame', 'school-id-front'),
  ScanKind.idBack: ScanSpec('School ID - back', 'ID SCAN', 1.586, 'Fit the back of your ID inside the frame', 'school-id-back'),
  ScanKind.cor: ScanSpec('Certificate of Registration (COR)', 'COR SCAN', 0.72, 'Fit the whole COR page inside the frame', 'cor'),
};

class ScanResult {
  ScanResult.done(File this.file, this.warnings) : error = null;
  ScanResult.failed(String this.error)
      : file = null,
        warnings = const [];
  final File? file;
  final List<String> warnings;
  final String? error;
}

class DocumentScanScreen extends StatefulWidget {
  const DocumentScanScreen({super.key, required this.kind});
  final ScanKind kind;

  @override
  State<DocumentScanScreen> createState() => _DocumentScanScreenState();
}

class _DocumentScanScreenState extends State<DocumentScanScreen>
    with WidgetsBindingObserver, SingleTickerProviderStateMixin {
  CameraController? _ctrl;
  bool _starting = true;
  bool _capturing = false;
  bool _torch = false;
  bool _autoWorks = true;

  final _analyzer = FrameAnalyzer();
  DateTime _lastFrame = DateTime.fromMillisecondsSinceEpoch(0);
  final DateTime _openedAt = DateTime.now();
  int _streak = 0;
  double _progress = 0;
  String _status = 'Looking for the document...';
  bool _slowHint = false;

  late final AnimationController _sweep =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 1800))..repeat(reverse: true);

  // geometry captured during build, used to map the on-screen frame onto the photo
  Size _body = Size.zero;
  Rect _frame = Rect.zero;

  ScanSpec get spec => scanSpecs[widget.kind]!;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    SystemChrome.setPreferredOrientations(const [DeviceOrientation.portraitUp]);
    _start();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _sweep.dispose();
    final c = _ctrl;
    _ctrl = null;
    c?.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.inactive || state == AppLifecycleState.paused) {
      final c = _ctrl;
      if (c != null) {
        _ctrl = null;
        c.dispose();
        if (mounted) setState(() => _starting = true);
      }
    } else if (state == AppLifecycleState.resumed && _ctrl == null && !_capturing) {
      _start();
    }
  }

  void _fail(String message) {
    if (mounted) Navigator.of(context).pop(ScanResult.failed(message));
  }

  Future<void> _start() async {
    setState(() => _starting = true);
    try {
      final cams = await availableCameras();
      if (cams.isEmpty) return _fail('No camera was found on this phone. Upload a photo instead.');
      final cam = cams.firstWhere((c) => c.lensDirection == CameraLensDirection.back, orElse: () => cams.first);
      final c = CameraController(cam, ResolutionPreset.high,
          enableAudio: false, imageFormatGroup: ImageFormatGroup.yuv420);
      await c.initialize();
      try {
        await c.lockCaptureOrientation(DeviceOrientation.portraitUp);
      } catch (_) {}
      try {
        await c.setFlashMode(FlashMode.off);
      } catch (_) {}
      try {
        await c.setFocusMode(FocusMode.auto);
      } catch (_) {}
      if (!mounted) {
        await c.dispose();
        return;
      }
      _ctrl = c;
      _torch = false;
      _streak = 0;
      _progress = 0;
      _analyzer.reset();
      setState(() => _starting = false);
      await _beginStream();
    } on CameraException catch (e) {
      final denied = e.code.startsWith('CameraAccess');
      _fail(denied
          ? 'Camera permission was blocked. Allow the camera in the phone settings, or upload a photo.'
          : 'The camera could not start. Upload a photo instead.');
    } catch (_) {
      _fail('The camera could not start. Upload a photo instead.');
    }
  }

  Future<void> _beginStream() async {
    final c = _ctrl;
    if (c == null || !c.value.isInitialized || c.value.isStreamingImages || !_autoWorks) return;
    try {
      await c.startImageStream(_onFrame);
    } catch (_) {
      // Live analysis is not available on this phone: the manual shutter still works.
      _autoWorks = false;
      if (mounted) setState(() => _status = 'Fit the document in the frame, then tap the button.');
    }
  }

  void _onFrame(CameraImage image) {
    if (_capturing || !mounted) return;
    final now = DateTime.now();
    if (now.difference(_lastFrame).inMilliseconds < 160) return; // ~6 analysed frames per second
    _lastFrame = now;

    FrameReport r;
    try {
      r = _analyzer.analyze(image);
    } catch (_) {
      _autoWorks = false;
      _ctrl?.stopImageStream().catchError((Object _) {});
      return;
    }

    String status;
    var good = false;
    if (r.dark) {
      status = 'Too dark - move to a brighter place or use the light.';
    } else if (r.glare) {
      status = 'Too much glare - tilt the document slightly.';
    } else if (r.noDocument) {
      status = 'Looking for the document...';
    } else if (r.moving) {
      status = 'Hold steady...';
    } else if (r.blurry(_analyzer.bestSharpness)) {
      status = 'Move a little closer / wait for focus...';
    } else {
      status = 'Scanning - hold still...';
      good = true;
    }

    _streak = good ? _streak + 1 : math.max(0, _streak - 2);
    final progress = (_streak / Tuning.goodFramesNeeded).clamp(0.0, 1.0).toDouble();
    final slow = now.difference(_openedAt).inSeconds >= 12;

    setState(() {
      _status = status;
      _progress = progress;
      _slowHint = slow;
    });
    if (_streak >= Tuning.goodFramesNeeded) _capture();
  }

  Future<void> _toggleTorch() async {
    final c = _ctrl;
    if (c == null || !c.value.isInitialized) return;
    try {
      await c.setFlashMode(_torch ? FlashMode.off : FlashMode.torch);
      setState(() => _torch = !_torch);
    } catch (_) {}
  }

  /// Fraction of the preview that the on-screen frame covers (with a little margin so the card edge is not cut).
  ({double u0, double v0, double u1, double v1}) _cropFractions(Size preview) {
    final pw = math.min(preview.width, preview.height);
    final ph = math.max(preview.width, preview.height);
    final scale = math.max(_body.width / pw, _body.height / ph);
    final dw = pw * scale, dh = ph * scale;
    final offX = (_body.width - dw) / 2, offY = (_body.height - dh) / 2;
    const pad = 0.03;
    final padX = _frame.width * pad, padY = _frame.height * pad;
    double f(double v) => v.clamp(0.0, 1.0).toDouble();
    return (
      u0: f((_frame.left - padX - offX) / dw),
      v0: f((_frame.top - padY - offY) / dh),
      u1: f((_frame.right + padX - offX) / dw),
      v1: f((_frame.bottom + padY - offY) / dh),
    );
  }

  Future<void> _capture() async {
    final c = _ctrl;
    if (c == null || _capturing || !c.value.isInitialized || _frame == Rect.zero) return;
    setState(() {
      _capturing = true;
      _progress = 1;
      _status = 'Saving the scan...';
    });
    try {
      if (c.value.isStreamingImages) await c.stopImageStream();
      final shot = await c.takePicture();
      final crop = _cropFractions(c.value.previewSize ?? const Size(1080, 1920));
      final dir = await getTemporaryDirectory();
      final out = '${dir.path}/${spec.baseName}-${DateTime.now().millisecondsSinceEpoch}.jpg';
      final saved = await cropToFile(
          src: shot.path, dst: out, u0: crop.u0, v0: crop.v0, u1: crop.u1, v1: crop.v1);
      final warns = await checkQuality(saved);
      try {
        File(shot.path).deleteSync(); // the full uncropped photo is not kept
      } catch (_) {}
      HapticFeedback.mediumImpact();
      if (!mounted) return;
      Navigator.of(context).pop(ScanResult.done(File(saved), warns));
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _capturing = false;
        _progress = 0;
        _streak = 0;
        _status = 'Could not save the photo. Try again.';
      });
      _analyzer.reset();
      await _beginStream();
    }
  }

  Rect _frameFor(Size s) {
    final maxW = s.width * 0.88, maxH = s.height * 0.58;
    var w = maxW, h = w / spec.ratio;
    if (h > maxH) {
      h = maxH;
      w = h * spec.ratio;
    }
    return Rect.fromCenter(center: Offset(s.width / 2, s.height * 0.43), width: w, height: h);
  }

  @override
  Widget build(BuildContext context) {
    final c = _ctrl;
    return Scaffold(
      backgroundColor: Colors.black,
      body: LayoutBuilder(builder: (context, box) {
        _body = box.biggest;
        _frame = _frameFor(_body);
        final ready = c != null && c.value.isInitialized && !_starting;

        return Stack(fit: StackFit.expand, children: [
          if (ready) _preview(c) else const SizedBox.expand(),
          if (ready) ...[
            CustomPaint(painter: _DimPainter(_frame)),
            CustomPaint(painter: _BracketPainter(_frame, _progress > 0 ? C.gold : Colors.white)),
            AnimatedBuilder(
              animation: _sweep,
              builder: (_, __) => Positioned(
                left: _frame.left + 8,
                width: _frame.width - 16,
                top: _frame.top + (_frame.height - 3) * _sweep.value,
                height: 3,
                child: Container(
                  decoration: BoxDecoration(
                    color: const Color(0xFFFF3B3B),
                    borderRadius: BorderRadius.circular(2),
                    boxShadow: const [BoxShadow(color: Color(0xAAFF3B3B), blurRadius: 10, spreadRadius: 1)],
                  ),
                ),
              ),
            ),
            // status line above the frame
            Positioned(
              left: 20,
              right: 20,
              top: _frame.top - 58,
              child: Center(
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(color: Colors.black54, borderRadius: BorderRadius.circular(999)),
                  child: Text(_status,
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
                ),
              ),
            ),
            Positioned(
              left: 24,
              right: 24,
              top: _frame.bottom + 14,
              child: Text(spec.hint,
                  textAlign: TextAlign.center, style: const TextStyle(color: Colors.white70, fontSize: 14)),
            ),
          ] else
            const Center(child: CircularProgressIndicator(color: Colors.white)),
          // top bar
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
              child: Row(children: [
                IconButton(
                  onPressed: _capturing ? null : () => Navigator.of(context).pop(),
                  icon: const Icon(Icons.close, color: Colors.white),
                  tooltip: 'Close scanner',
                ),
                Expanded(
                  child: Text(spec.title,
                      textAlign: TextAlign.center,
                      style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 16)),
                ),
                IconButton(
                  onPressed: ready && !_capturing ? _toggleTorch : null,
                  icon: Icon(_torch ? Icons.flash_on : Icons.flash_off, color: _torch ? C.gold : Colors.white),
                  tooltip: 'Light',
                ),
              ]),
            ),
          ),
          // bottom: progress ring + manual shutter
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: SafeArea(
              child: Padding(
                padding: const EdgeInsets.only(bottom: 14),
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  if (_slowHint && !_capturing)
                    const Padding(
                      padding: EdgeInsets.only(bottom: 8),
                      child: Text('Taking long? Tap the white button to take the photo now.',
                          style: TextStyle(color: C.gold, fontSize: 13)),
                    ),
                  SizedBox(
                    width: 84,
                    height: 84,
                    child: Stack(alignment: Alignment.center, children: [
                      SizedBox(
                        width: 84,
                        height: 84,
                        child: CircularProgressIndicator(
                          value: _capturing ? null : _progress,
                          strokeWidth: 5,
                          color: C.gold,
                          backgroundColor: Colors.white24,
                        ),
                      ),
                      GestureDetector(
                        onTap: ready && !_capturing ? _capture : null,
                        child: Semantics(
                          button: true,
                          label: 'Take photo',
                          child: Container(
                            width: 62,
                            height: 62,
                            decoration: const BoxDecoration(color: Colors.white, shape: BoxShape.circle),
                          ),
                        ),
                      ),
                    ]),
                  ),
                  const SizedBox(height: 8),
                  Text(spec.short,
                      style: const TextStyle(color: Colors.white54, letterSpacing: 2, fontSize: 12, fontWeight: FontWeight.w700)),
                ]),
              ),
            ),
          ),
          if (_capturing) Container(color: Colors.black45),
        ]);
      }),
    );
  }

  Widget _preview(CameraController c) {
    final ps = c.value.previewSize ?? const Size(1920, 1080);
    final pw = math.min(ps.width, ps.height);
    final ph = math.max(ps.width, ps.height);
    return ClipRect(
      child: FittedBox(
        fit: BoxFit.cover,
        child: SizedBox(width: pw, height: ph, child: CameraPreview(c)),
      ),
    );
  }
}

/// Darkens everything outside the scan frame.
class _DimPainter extends CustomPainter {
  _DimPainter(this.frame);
  final Rect frame;
  @override
  void paint(Canvas canvas, Size size) {
    final all = Path()..addRect(Offset.zero & size);
    final hole = Path()..addRRect(RRect.fromRectAndRadius(frame, const Radius.circular(14)));
    canvas.drawPath(Path.combine(PathOperation.difference, all, hole), Paint()..color = const Color(0x99000000));
  }

  @override
  bool shouldRepaint(_DimPainter old) => old.frame != frame;
}

/// Four corner brackets around the frame.
class _BracketPainter extends CustomPainter {
  _BracketPainter(this.frame, this.color);
  final Rect frame;
  final Color color;
  @override
  void paint(Canvas canvas, Size size) {
    final p = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 4
      ..strokeCap = StrokeCap.round;
    const len = 28.0;
    void corner(Offset o, double dx, double dy) {
      canvas.drawLine(o, o + Offset(dx * len, 0), p);
      canvas.drawLine(o, o + Offset(0, dy * len), p);
    }

    corner(frame.topLeft, 1, 1);
    corner(frame.topRight, -1, 1);
    corner(frame.bottomLeft, 1, -1);
    corner(frame.bottomRight, -1, -1);
  }

  @override
  bool shouldRepaint(_BracketPainter old) => old.frame != frame || old.color != color;
}
