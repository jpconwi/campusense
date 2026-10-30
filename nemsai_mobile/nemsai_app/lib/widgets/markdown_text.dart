/// markdown_text.dart - the small Markdown subset the AI answers use: paragraphs, "- " / "1." lists,
/// **bold** and http(s) links. Everything is plain Text, so nothing unsafe can run.
library;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../theme.dart';

final _urlRe = RegExp(r'''(https?://[^\s<>"]*[^\s<>".,;:!?)\]'])''');

String linkLabel(String url) {
  final u = Uri.tryParse(url);
  if (u == null || u.host.isEmpty) return url;
  if (u.host.endsWith('nemsu.edu.ph') && u.path.startsWith('/news/')) return 'Read the full article \u2197';
  return u.host + (u.path.length > 1 ? '/\u2026' : '');
}

class MarkdownText extends StatefulWidget {
  const MarkdownText(this.text, {super.key, this.color = C.ink});
  final String text;
  final Color color;

  @override
  State<MarkdownText> createState() => _MarkdownTextState();
}

class _MarkdownTextState extends State<MarkdownText> {
  final List<TapGestureRecognizer> _taps = [];

  void _disposeTaps() {
    for (final t in _taps) {
      t.dispose();
    }
    _taps.clear();
  }

  @override
  void dispose() {
    _disposeTaps();
    super.dispose();
  }

  Future<void> _open(String url) async {
    final uri = Uri.tryParse(url);
    if (uri == null) return;
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  List<InlineSpan> _linked(String text, TextStyle base) {
    final spans = <InlineSpan>[];
    var last = 0;
    for (final m in _urlRe.allMatches(text)) {
      if (m.start > last) spans.add(TextSpan(text: text.substring(last, m.start), style: base));
      final url = m.group(0)!;
      final tap = TapGestureRecognizer()..onTap = () => _open(url);
      _taps.add(tap);
      spans.add(TextSpan(
        text: linkLabel(url),
        recognizer: tap,
        style: base.copyWith(color: C.blue, decoration: TextDecoration.underline),
      ));
      last = m.end;
    }
    if (last < text.length) spans.add(TextSpan(text: text.substring(last), style: base));
    return spans;
  }

  /// Splits on **bold** while keeping the markers' content.
  List<InlineSpan> _rich(String text, TextStyle base) {
    final spans = <InlineSpan>[];
    final bold = RegExp(r'\*\*(.+?)\*\*');
    var last = 0;
    for (final m in bold.allMatches(text)) {
      if (m.start > last) spans.addAll(_linked(text.substring(last, m.start), base));
      spans.addAll(_linked(m.group(1)!, base.copyWith(fontWeight: FontWeight.w700)));
      last = m.end;
    }
    if (last < text.length) spans.addAll(_linked(text.substring(last), base));
    return spans;
  }

  @override
  Widget build(BuildContext context) {
    _disposeTaps();
    final base = TextStyle(color: widget.color, fontSize: 15, height: 1.45);
    final blocks = <Widget>[];
    final para = <String>[];
    final items = <String>[];
    String? listType;
    String? listStart;

    void flushPara() {
      if (para.isEmpty) return;
      blocks.add(Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text.rich(TextSpan(children: _rich(para.join('\n'), base))),
      ));
      para.clear();
    }

    void closeList() {
      if (listType == null) return;
      final start = int.tryParse(listStart ?? '1') ?? 1;
      blocks.add(Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          for (var i = 0; i < items.length; i++)
            Padding(
              padding: const EdgeInsets.only(bottom: 3),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                SizedBox(width: 24, child: Text(listType == 'ol' ? '${start + i}.' : '\u2022', style: base)),
                Expanded(child: Text.rich(TextSpan(children: _rich(items[i], base)))),
              ]),
            ),
        ]),
      ));
      items.clear();
      listType = null;
      listStart = null;
    }

    final olRe = RegExp(r'^(\d+)\.\s+(.*)');
    final ulRe = RegExp(r'^[-*]\s+(.*)');
    for (final raw in widget.text.split('\n')) {
      final line = raw.trim();
      final ol = olRe.firstMatch(line);
      final ul = ulRe.firstMatch(line);
      if (ol != null || ul != null) {
        flushPara();
        final type = ol != null ? 'ol' : 'ul';
        if (listType != type) {
          closeList();
          listType = type;
          listStart = ol?.group(1);
        }
        items.add(ol != null ? ol.group(2)! : ul!.group(1)!);
      } else if (line.isEmpty) {
        flushPara();
        closeList();
      } else {
        closeList();
        para.add(line);
      }
    }
    flushPara();
    closeList();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: blocks);
  }
}
