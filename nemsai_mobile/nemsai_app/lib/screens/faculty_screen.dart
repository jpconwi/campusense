/// faculty_screen.dart - instructors report an absence / mark themselves available (port of Faculty.jsx).
library;

import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/record_form.dart';
import '../widgets/skeleton.dart';

class FacultyScreen extends StatefulWidget {
  const FacultyScreen({super.key});
  @override
  State<FacultyScreen> createState() => _FacultyScreenState();
}

class _FacultyScreenState extends State<FacultyScreen> {
  List<Map<String, dynamic>>? _rows;
  bool _open = false;
  Map<String, dynamic>? _result;
  bool _marking = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final d = await api.get('/api/me/faculty');
      if (mounted) {
        setState(() => _rows = ((d['rows'] as List?) ?? const []).map((e) => Map<String, dynamic>.from(e as Map)).toList());
      }
    } on ApiError {
      if (mounted) setState(() => _rows = []);
    }
  }

  Future<void> _markAvailable() async {
    setState(() => _marking = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      await api.post('/api/faculty/available');
      messenger.showSnackBar(const SnackBar(content: Text('You are marked as available.')));
      await _load();
    } on ApiError {
      messenger.showSnackBar(const SnackBar(content: Text('Could not update your status.')));
    } finally {
      if (mounted) setState(() => _marking = false);
    }
  }

  void _done(Map<String, dynamic> res) {
    setState(() => _result = res);
    Future.delayed(const Duration(milliseconds: 1600), () {
      if (!mounted) return;
      _load();
      setState(() {
        _open = false;
        _result = null;
      });
    });
  }

  Future<void> _pdf(Object? id) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await api.openPdf('/api/pdf/faculty/$id', 'faculty-$id');
    } on ApiError catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final rows = _rows;
    return AppScaffold(
      title: 'Faculty Availability',
      current: '/faculty',
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          children: [
            const PageTitle('Faculty Availability',
                intro: 'Report when you cannot come to school. Students asking the AI will see your recorded status and expected return date (not your reason).'),
            FilledButton.icon(
              onPressed: () => setState(() => _open = !_open),
              icon: Icon(_open ? Icons.close : Icons.add),
              label: Text(_open ? 'Close form' : 'New absence report'),
            ),
            const SizedBox(height: 10),
            OutlinedButton.icon(
              onPressed: _marking ? null : _markAvailable,
              icon: const Icon(Icons.check_circle_outline),
              label: Text(_marking ? 'Updating...' : 'I am back - mark me available'),
            ),
            if (_open) ...[
              const SizedBox(height: 14),
              Panel(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  RecordForm(kind: 'faculty', onSuccess: _done),
                  if (_result != null) ...[const SizedBox(height: 12), SuccessCard(result: _result!)],
                ]),
              ),
            ],
            const SizedBox(height: 22),
            const Text('Your reports',
                style: TextStyle(fontFamily: serif, fontSize: 19, fontWeight: FontWeight.w700, color: C.blueDeep)),
            const SizedBox(height: 8),
            if (rows == null)
              const SizedBox(height: 380, child: ListSkeleton(rows: 3, heading: false))
            else if (rows.isEmpty)
              const EmptyState(title: 'No faculty reports yet')
            else
              for (final r in rows) ...[
                Panel(
                  padding: const EdgeInsets.all(14),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Row(children: [
                      Text('#${padId(r['id'])}', style: const TextStyle(fontWeight: FontWeight.w800, color: C.blueDeep)),
                      const Spacer(),
                      StatusBadge('${r['status'] ?? ''}'),
                    ]),
                    const SizedBox(height: 8),
                    _line('Reason', '${r['reason'] ?? ''}'),
                    _line('Absence date', '${r['start_date'] ?? ''}'),
                    _line('Expected return', '${r['expected_return'] ?? ''}'),
                    _line('Submitted', '${r['submitted_at'] ?? ''}'),
                    TextButton.icon(
                      onPressed: () => _pdf(r['id']),
                      icon: const Icon(Icons.picture_as_pdf_outlined, size: 18),
                      label: const Text('PDF'),
                    ),
                  ]),
                ),
                const SizedBox(height: 10),
              ],
          ],
        ),
      ),
    );
  }

  Widget _line(String k, String v) => v.isEmpty
      ? const SizedBox.shrink()
      : Padding(
          padding: const EdgeInsets.symmetric(vertical: 3),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            SizedBox(width: 104, child: Text(k, style: const TextStyle(color: C.muted, fontSize: 13))),
            Expanded(child: Text(v, style: const TextStyle(height: 1.35))),
          ]),
        );
}
