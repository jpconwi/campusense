/// photo_report_card.dart - shown in the chat after a photo is sent (port of PhotoReportCard.jsx).
/// Shows what the AI thinks (as a guess), asks the follow-up questions, lets the person correct
/// everything by typing and sends the report to the administrators.
library;

import 'dart:io';

import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../theme.dart';
import 'common.dart';

const _fields = [
  ['location', 'Where did this happen?', 'e.g. CITE building, 2nd floor'],
  ['noticed_when', 'When did you notice it?', 'e.g. this morning'],
  ['observed_cause', 'Do you know what caused it?', 'or write "I don\'t know"'],
];
const _asked = {'location': 'location', 'noticed_when': 'when', 'observed_cause': 'cause'};
const _confidence = {'high': 'fairly sure', 'medium': 'somewhat sure', 'low': 'not sure'};
const _notAReport = {
  'people': 'This looks like a photo of people.',
  'meme_or_screenshot': 'This looks like a picture, meme or screenshot.',
  'unrelated': "I can't see anything related to the campus in this photo.",
};

class PhotoReportCard extends StatefulWidget {
  const PhotoReportCard({
    super.key,
    required this.result,
    required this.preview,
    required this.onMessage,
    required this.onSent,
    required this.onDiscarded,
  });
  final Map<String, dynamic> result;
  final File? preview;
  final void Function(String text) onMessage;
  final void Function(Map<String, dynamic> result) onSent;
  final VoidCallback onDiscarded;

  @override
  State<PhotoReportCard> createState() => _PhotoReportCardState();
}

class _PhotoReportCardState extends State<PhotoReportCard> {
  late Map<String, dynamic> _result = widget.result;
  final Map<String, TextEditingController> _c = {};
  String _busy = '';
  String _error = '';
  String _state = 'open'; // open | sent | discarded
  bool _expanded = false;

  @override
  void initState() {
    super.initState();
    _fill(_result);
  }

  void _fill(Map<String, dynamic> r) {
    final v = Map<String, dynamic>.from((r['values'] as Map?) ?? {});
    for (final k in ['description', 'location', 'noticed_when', 'observed_cause']) {
      final text = '${v[k] ?? ''}';
      final existing = _c[k];
      if (existing == null) {
        _c[k] = TextEditingController(text: text);
      } else {
        existing.text = text;
      }
    }
  }

  @override
  void dispose() {
    for (final c in _c.values) {
      c.dispose();
    }
    super.dispose();
  }

  Map<String, dynamic> get _values => Map<String, dynamic>.from((_result['values'] as Map?) ?? {});
  bool get _dirty => _c.entries.any((e) => e.value.text != '${_values[e.key] ?? ''}');
  List<Map<String, dynamic>> get _questions =>
      ((_result['questions'] as List?) ?? const []).map((e) => Map<String, dynamic>.from(e as Map)).toList();
  Map<String, dynamic> get _analysis => Map<String, dynamic>.from((_result['analysis'] as Map?) ?? {});

  Future<Map<String, String>> _fieldsMap() async =>
      {for (final e in _c.entries) e.key: e.value.text.trim()};

  Future<void> _check() async {
    setState(() {
      _busy = 'check';
      _error = '';
    });
    try {
      final f = await _fieldsMap();
      f['draft_id'] = '${_result['draft_id']}';
      final data = await api.postForm('/api/reports/photo/analyze', await api.buildForm(f));
      setState(() {
        _result = data;
        _fill(data);
      });
      widget.onMessage('${data['message'] ?? ''}');
    } on ApiError catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = '');
    }
  }

  Future<void> _send() async {
    setState(() {
      _busy = 'send';
      _error = '';
    });
    try {
      final data = await api.postForm('/api/reports/photo/${_result['draft_id']}/submit', await api.buildForm(await _fieldsMap()));
      setState(() => _state = 'sent');
      widget.onSent(data);
    } on ApiError catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = '');
    }
  }

  Future<void> _discard() async {
    setState(() {
      _busy = 'discard';
      _error = '';
    });
    try {
      await api.delete('/api/reports/photo/${_result['draft_id']}');
      setState(() => _state = 'discarded');
      widget.onDiscarded();
    } on ApiError catch (e) {
      setState(() {
        _error = e.message;
        _busy = '';
      });
    }
  }

  Widget _thumb() => widget.preview == null
      ? const SizedBox.shrink()
      : Padding(
          padding: const EdgeInsets.only(right: 12),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(10),
            child: Image.file(widget.preview!, width: 64, height: 64, fit: BoxFit.cover),
          ),
        );

  @override
  Widget build(BuildContext context) {
    if (_state == 'sent') {
      return const Panel(color: C.okBg, child: Text.rich(TextSpan(children: [
        TextSpan(text: 'Report sent. ', style: TextStyle(fontWeight: FontWeight.w700)),
        TextSpan(text: 'An administrator will review it.'),
      ])));
    }
    if (_state == 'discarded') return const Panel(child: Text('Photo removed. Nothing was sent.'));

    final a = _analysis;
    final kind = '${a['image_kind'] ?? ''}';
    if (_result['outcome'] == 'no_issue' && _notAReport.containsKey(kind) && !_expanded) {
      return Panel(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            _thumb(),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('Not a campus report',
                    style: TextStyle(fontFamily: serif, fontSize: 17, fontWeight: FontWeight.w700, color: C.blueDeep)),
                const SizedBox(height: 2),
                Text('${_notAReport[kind]} Nothing was sent to the administrators.',
                    style: const TextStyle(color: C.muted, fontSize: 13.5)),
              ]),
            ),
          ]),
          if (_error.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 8), child: Message(_error, isError: true)),
          const SizedBox(height: 10),
          Wrap(spacing: 8, runSpacing: 8, children: [
            FilledButton(onPressed: _busy.isNotEmpty ? null : _discard, child: Text(_busy == 'discard' ? 'Removing...' : 'Remove photo')),
            OutlinedButton(onPressed: _busy.isNotEmpty ? null : () => setState(() => _expanded = true), child: const Text('It is a campus problem')),
          ]),
        ]),
      );
    }

    final asked = _questions.map((q) => '${q['key']}').toSet();
    String? questionFor(String key) {
      for (final q in _questions) {
        if ('${q['key']}' == _asked[key]) return '${q['question']}';
      }
      return null;
    }

    final descQ = _questions.where((q) => q['key'] == 'description').map((q) => '${q['question']}').toList();
    final observations = ((a['observations'] as List?) ?? const []).map((e) => '$e').toList();
    final canSubmit = _result['can_submit'] == true;
    final checksLeft = (_result['checks_left'] as num?)?.toInt() ?? 0;
    final busy = _busy.isNotEmpty;

    return Panel(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          _thumb(),
          const Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('Your photo report',
                  style: TextStyle(fontFamily: serif, fontSize: 17, fontWeight: FontWeight.w700, color: C.blueDeep)),
              SizedBox(height: 2),
              Text('Nothing is sent to the administrators until you press Send report.',
                  style: TextStyle(color: C.muted, fontSize: 13)),
            ]),
          ),
        ]),
        if (a['urgent'] == true) ...[
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: const Color(0xFFFBE0E2),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: C.error),
            ),
            child: const Text(
              'Possible safety hazard. Keep away from it and tell campus security or the nearest staff member now if '
              'anyone is in danger. This report will be marked for priority review.',
              style: TextStyle(color: C.error, fontSize: 13.5),
            ),
          ),
        ],
        if (observations.isNotEmpty || '${a['issue_title'] ?? ''}'.isNotEmpty)
          Theme(
            data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
            child: ExpansionTile(
              tilePadding: EdgeInsets.zero,
              childrenPadding: EdgeInsets.zero,
              title: const Text('What the AI noticed (AI guess, not verified)',
                  style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: C.blue)),
              expandedCrossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if ('${a['issue_title'] ?? ''}'.isNotEmpty)
                  Text('${a['issue_title']} (${_confidence['${a['confidence']}'] ?? 'not sure'})',
                      style: const TextStyle(fontWeight: FontWeight.w700)),
                for (final o in observations) Text('• $o'),
                if ('${a['check_explanation'] ?? ''}'.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Text('${a['check_explanation']}', style: const TextStyle(color: C.muted, fontSize: 13)),
                  ),
                const SizedBox(height: 6),
              ],
            ),
          ),
        const SizedBox(height: 10),
        TextField(
          controller: _c['description'],
          enabled: !busy,
          maxLength: 2000,
          minLines: 3,
          maxLines: 6,
          decoration: InputDecoration(
            labelText: descQ.isNotEmpty ? descQ.first : 'Your description',
            hintText: 'Type what happened',
            floatingLabelBehavior: FloatingLabelBehavior.always,
          ),
        ),
        for (final f in _fields) ...[
          const SizedBox(height: 10),
          TextField(
            controller: _c[f[0]],
            enabled: !busy,
            maxLength: f[0] == 'observed_cause' ? 500 : 120,
            decoration: InputDecoration(
              labelText: questionFor(f[0]) ?? f[1],
              hintText: f[2],
              counterText: '',
              floatingLabelBehavior: FloatingLabelBehavior.always,
              enabledBorder: asked.contains(_asked[f[0]])
                  ? OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: const BorderSide(color: C.gold, width: 1.6))
                  : null,
            ),
          ),
        ],
        if (_error.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 10), child: Message(_error, isError: true)),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          FilledButton(
            onPressed: busy || !canSubmit ? null : _send,
            child: Text(_busy == 'send' ? 'Sending...' : 'Send report'),
          ),
          OutlinedButton(
            onPressed: busy || !_dirty || checksLeft < 1 ? null : _check,
            child: Text(_busy == 'check' ? 'Checking...' : 'Check again'),
          ),
          OutlinedButton(onPressed: busy ? null : _discard, child: const Text('Discard photo')),
        ]),
        if (!canSubmit)
          const Padding(
            padding: EdgeInsets.only(top: 8),
            child: Text('Add a short description above and press Check again to continue.',
                style: TextStyle(color: C.muted, fontSize: 13)),
          ),
      ]),
    );
  }
}
