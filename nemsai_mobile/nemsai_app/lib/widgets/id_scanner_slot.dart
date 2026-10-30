/// id_scanner_slot.dart - one document slot (ID front / ID back / COR) with a choice:
/// "Scan with camera" (built-in auto-scanner) or "Upload" (from the gallery).
/// If the phone's camera is missing or broken, only Upload is offered.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:path_provider/path_provider.dart';

import '../config.dart';
import '../screens/document_scan_screen.dart';
import '../theme.dart';
import '../util/image_tools.dart';

class IdScannerSlot extends StatefulWidget {
  const IdScannerSlot({
    super.key,
    required this.kind,
    required this.file,
    required this.onChanged,
    this.required = false,
    this.disabled = false,
  });

  final ScanKind kind;
  final File? file;
  final ValueChanged<File?> onChanged;
  final bool required;
  final bool disabled;

  @override
  State<IdScannerSlot> createState() => _IdScannerSlotState();
}

class _IdScannerSlotState extends State<IdScannerSlot> with SingleTickerProviderStateMixin {
  bool? _cameraOk; // null = still checking
  bool _blocked = false; // the scanner screen reported a camera problem
  String _error = '';
  String _note = '';
  List<String> _warns = const [];
  bool _busy = false;

  late final AnimationController _idle =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 2200))..repeat(reverse: true);

  ScanSpec get spec => scanSpecs[widget.kind]!;

  @override
  void initState() {
    super.initState();
    CameraProbe.available().then((ok) {
      if (mounted) setState(() => _cameraOk = ok);
    });
  }

  @override
  void dispose() {
    _idle.dispose();
    super.dispose();
  }

  Future<void> _scan() async {
    setState(() {
      _error = '';
      _note = '';
    });
    final result = await Navigator.of(context).push<ScanResult>(
      MaterialPageRoute(fullscreenDialog: true, builder: (_) => DocumentScanScreen(kind: widget.kind)),
    );
    if (!mounted || result == null) return;
    if (result.error != null) {
      CameraProbe.reset();
      setState(() {
        _blocked = true;
        _note = result.error!;
      });
      return;
    }
    setState(() => _warns = result.warnings);
    widget.onChanged(result.file);
  }

  Future<void> _upload() async {
    setState(() {
      _error = '';
      _busy = true;
    });
    try {
      final picked = await ImagePicker().pickImage(
        source: ImageSource.gallery,
        maxWidth: 2400,
        maxHeight: 2400,
        imageQuality: 90,
      );
      if (picked == null) return;
      var path = picked.path;
      if (sniffImage(path) == null) {
        setState(() => _error = 'Choose a JPG, PNG or WEBP photo.');
        return;
      }
      if (File(path).lengthSync() > AppConfig.maxImageBytes) {
        final dir = await getTemporaryDirectory();
        path = await shrinkToJpeg(path, '${dir.path}/${spec.baseName}-${DateTime.now().millisecondsSinceEpoch}.jpg');
      }
      if (File(path).lengthSync() > AppConfig.maxImageBytes) {
        setState(() => _error = 'That photo is over 5 MB. Choose a smaller one.');
        return;
      }
      final warns = await checkQuality(path);
      if (!mounted) return;
      setState(() => _warns = warns);
      widget.onChanged(File(path));
    } catch (_) {
      if (mounted) setState(() => _error = 'That photo could not be opened. Try another one.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _remove() {
    setState(() {
      _warns = const [];
      _error = '';
    });
    widget.onChanged(null);
  }

  @override
  Widget build(BuildContext context) {
    final file = widget.file;
    final canScan = _cameraOk == true && !_blocked;
    final noCameraNote = _cameraOk == false
        ? 'No working camera was found on this phone. You can upload a photo instead.'
        : '';
    final note = _note.isNotEmpty ? _note : noCameraNote;
    final disabled = widget.disabled || _busy;
    final portrait = spec.ratio < 1;

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: file != null ? C.okLine : C.line),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: Text(spec.title, style: const TextStyle(fontWeight: FontWeight.w700, color: C.blueDeep))),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
            decoration: BoxDecoration(
              color: file != null ? C.okBg : C.blueSoft,
              borderRadius: BorderRadius.circular(999),
            ),
            child: Text(
              file != null ? 'Captured' : (widget.required ? 'Required' : 'Optional'),
              style: TextStyle(
                  fontSize: 12, fontWeight: FontWeight.w700, color: file != null ? const Color(0xFF1E6B2A) : C.blue),
            ),
          ),
        ]),
        const SizedBox(height: 10),
        Center(
          child: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: portrait ? 220 : 340),
            child: AspectRatio(
              aspectRatio: spec.ratio,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(12),
                child: file != null
                    ? Image.file(file, fit: BoxFit.cover, errorBuilder: (_, __, ___) => const Center(child: Icon(Icons.broken_image_outlined)))
                    : _idleStage(),
              ),
            ),
          ),
        ),
        if (_error.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(_error, style: const TextStyle(color: C.error, fontSize: 13)),
          )
        else if (note.isNotEmpty && file == null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(note, style: const TextStyle(color: Color(0xFF8A6100), fontSize: 13)),
          ),
        if (_error.isEmpty && file != null)
          for (final w in _warns)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Icon(Icons.info_outline, size: 16, color: Color(0xFF8A6100)),
                const SizedBox(width: 6),
                Expanded(child: Text(w, style: const TextStyle(color: Color(0xFF8A6100), fontSize: 13))),
              ]),
            ),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          if (canScan)
            FilledButton.icon(
              onPressed: disabled ? null : _scan,
              icon: Icon(file != null ? Icons.refresh : Icons.photo_camera_outlined, size: 20),
              label: Text(file != null ? 'Retake' : 'Scan with camera'),
            ),
          canScan
              ? OutlinedButton.icon(
                  onPressed: disabled ? null : _upload,
                  icon: const Icon(Icons.upload_outlined, size: 20),
                  label: const Text('Upload'),
                )
              : FilledButton.icon(
                  onPressed: disabled ? null : _upload,
                  icon: const Icon(Icons.upload_outlined, size: 20),
                  label: Text(file != null ? 'Choose another' : 'Upload'),
                ),
          if (file != null)
            OutlinedButton.icon(
              style: OutlinedButton.styleFrom(foregroundColor: C.error),
              onPressed: disabled ? null : _remove,
              icon: const Icon(Icons.close, size: 20),
              label: const Text('Remove'),
            ),
        ]),
      ]),
    );
  }

  Widget _idleStage() {
    return Container(
      color: C.blueDeep,
      child: Stack(fit: StackFit.expand, children: [
        Center(
          child: Icon(widget.kind == ScanKind.cor ? Icons.description_outlined : Icons.badge_outlined,
              size: 54, color: const Color(0x66FFFFFF)),
        ),
        AnimatedBuilder(
          animation: _idle,
          builder: (context, _) => Align(
            alignment: Alignment(0, -1 + 2 * _idle.value),
            child: Container(
              height: 3,
              margin: const EdgeInsets.symmetric(horizontal: 10),
              decoration: BoxDecoration(
                color: const Color(0xFFFF3B3B),
                borderRadius: BorderRadius.circular(2),
                boxShadow: const [BoxShadow(color: Color(0x88FF3B3B), blurRadius: 8)],
              ),
            ),
          ),
        ),
      ]),
    );
  }
}

