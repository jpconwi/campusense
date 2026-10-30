/// record_form.dart - one place that defines every form (concern, report, feedback, reservation,
/// faculty). Port of the website's RecordForm.jsx. Name and email are NOT typed by the user:
/// the server takes them from the signed-in Google account.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../api/api_client.dart';
import '../api/auth_state.dart';
import '../config.dart';
import '../theme.dart';
import '../util/image_tools.dart';
import 'common.dart';

const _concernTypes = ['Equipment', 'Electrical', 'Plumbing', 'Furniture', 'Building / Structure', 'Cleanliness', 'Safety', 'Other'];
const _reportTypes = ['Maintenance', 'Safety', 'Security', 'Cleanliness', 'Equipment', 'Lost & Found', 'Other'];
const _feedbackTypes = ['Compliment', 'Suggestion', 'Complaint', 'Other'];

enum FieldType { text, textarea, select, date, time, file }

class FieldSpec {
  const FieldSpec(this.name, this.label, this.type,
      {this.required = false, this.hint, this.options = const [], this.today = false, this.list = false});
  final String name;
  final String label;
  final FieldType type;
  final bool required;
  final String? hint;
  final List<String> options;
  final bool today; // date defaults to today (and has min/max limits)
  final bool list; // text field with facility suggestions
}

class FormSpec {
  const FormSpec(this.title, this.endpoint, this.desc, this.fields);
  final String title;
  final String endpoint;
  final String desc;
  final List<FieldSpec> fields;
}

const forms = <String, FormSpec>{
  'concern': FormSpec('Concern Form', '/api/concerns', 'Describe the problem so it can be checked.', [
    FieldSpec('location', 'Location / Area', FieldType.text, required: true, hint: 'e.g. CITE building'),
    FieldSpec('room', 'Room', FieldType.text, hint: 'e.g. Room 204 (optional)'),
    FieldSpec('concern_type', 'Concern type', FieldType.select, required: true, options: _concernTypes),
    FieldSpec('description', 'Description', FieldType.textarea, required: true, hint: 'What is the problem?'),
    FieldSpec('concern_date', 'Date', FieldType.date, required: true, today: true),
    FieldSpec('image', 'Photo (optional, PNG/JPG/WEBP, max 5 MB)', FieldType.file),
  ]),
  'report': FormSpec('Report Form', '/api/reports', 'Submit a campus report.', [
    FieldSpec('location', 'Location', FieldType.text, required: true),
    FieldSpec('area', 'Area', FieldType.text, hint: 'optional'),
    FieldSpec('room', 'Room', FieldType.text, hint: 'optional'),
    FieldSpec('report_type', 'Report type', FieldType.select, required: true, options: _reportTypes),
    FieldSpec('description', 'Description', FieldType.textarea, required: true),
    FieldSpec('report_date', 'Date', FieldType.date, required: true, today: true),
    FieldSpec('image', 'Photo (optional, PNG/JPG/WEBP, max 5 MB)', FieldType.file),
  ]),
  'feedback': FormSpec('Feedback Form', '/api/feedback', 'Share your feedback about a campus area or facility.', [
    FieldSpec('area', 'Area / Facility', FieldType.text, required: true, hint: 'e.g. Library'),
    FieldSpec('feedback_type', 'Feedback type', FieldType.select, required: true, options: _feedbackTypes),
    FieldSpec('message', 'Message', FieldType.textarea, required: true),
    FieldSpec('feedback_date', 'Date', FieldType.date, required: true, today: true),
  ]),
  'reservation': FormSpec('Reservation Form', '/api/reservations',
      'Your request stays Pending until an administrator approves it.', [
    FieldSpec('facility', 'Facility / Room', FieldType.text, required: true, list: true),
    FieldSpec('purpose', 'Purpose', FieldType.text, required: true),
    FieldSpec('reservation_date', 'Date', FieldType.date, required: true, today: true),
    FieldSpec('start_time', 'Start time', FieldType.time, required: true),
    FieldSpec('end_time', 'End time', FieldType.time, required: true),
    FieldSpec('additional_info', 'Additional information', FieldType.textarea, hint: 'optional'),
  ]),
  'faculty': FormSpec('Faculty Availability Form', '/api/faculty/submit',
      'Fill in all fields so your availability report can be recorded.', [
    FieldSpec('reason', 'Reason', FieldType.textarea, required: true, hint: 'Why are you unable to attend?'),
    FieldSpec('start_date', 'Date of absence', FieldType.date, required: true, today: true),
    FieldSpec('expected_return', 'Expected date to return', FieldType.date, required: true, today: true),
  ]),
};

DateTime _today() {
  final n = DateTime.now();
  return DateTime(n.year, n.month, n.day);
}

/// Date limits the website applies: reservations and absence start can't be in the past,
/// other dates can't be in the future, the return date is free.
({DateTime first, DateTime last}) _dateLimits(String kind, FieldSpec f) {
  final t = _today();
  final far = DateTime(t.year + 3, t.month, t.day);
  if (kind == 'reservation' || f.name == 'start_date') return (first: t, last: far);
  if (f.name == 'expected_return') return (first: DateTime(2020), last: far);
  return (first: DateTime(2020), last: t);
}

class SuccessCard extends StatelessWidget {
  const SuccessCard({super.key, required this.result});
  final Map<String, dynamic> result;

  @override
  Widget build(BuildContext context) {
    final pdf = result['pdf_url'];
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: C.okBg,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: C.okLine),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('${result['message'] ?? 'Submitted.'}', style: const TextStyle(fontWeight: FontWeight.w700)),
        const SizedBox(height: 4),
        Text('Reference: #${result['id']}\nStatus: ${result['status']}'
            '${result['expected_return'] != null ? '\nExpected return: ${result['expected_return']}' : ''}'),
        if (pdf is String && pdf.isNotEmpty)
          TextButton.icon(
            style: TextButton.styleFrom(padding: EdgeInsets.zero, alignment: Alignment.centerLeft),
            onPressed: () async {
              final messenger = ScaffoldMessenger.of(context);
              try {
                await api.openPdf(pdf, 'report-${result['id']}');
              } on ApiError catch (e) {
                messenger.showSnackBar(SnackBar(content: Text(e.message)));
              }
            },
            icon: const Icon(Icons.picture_as_pdf_outlined, size: 18),
            label: const Text('Open PDF report'),
          ),
      ]),
    );
  }
}

/// props: kind (concern / report / feedback / reservation / faculty), prefill, onSuccess(result)
class RecordForm extends StatefulWidget {
  const RecordForm({super.key, required this.kind, this.prefill, this.onSuccess});
  final String kind;
  final Map<String, dynamic>? prefill;
  final void Function(Map<String, dynamic> result)? onSuccess;

  @override
  State<RecordForm> createState() => _RecordFormState();
}

class _RecordFormState extends State<RecordForm> {
  late final FormSpec spec = forms[widget.kind]!;
  final Map<String, String> _values = {};
  final Map<String, TextEditingController> _ctl = {};
  File? _photo;
  final Set<String> _invalid = {};
  String _error = '';
  bool _busy = false;
  bool _done = false;

  @override
  void initState() {
    super.initState();
    for (final f in spec.fields) {
      if (f.type == FieldType.file) continue;
      var v = f.today && f.type == FieldType.date ? isoDate(_today()) : '';
      final pre = widget.prefill?[f.name];
      if (pre is String && pre.isNotEmpty) v = pre;
      if (f.type == FieldType.select && v.isNotEmpty && !f.options.contains(v)) {
        _values['${f.name}_other'] = v.length > 50 ? v.substring(0, 50) : v;
        v = 'Other';
      }
      _values[f.name] = v;
      if (f.type == FieldType.text || f.type == FieldType.textarea || f.type == FieldType.date || f.type == FieldType.time) {
        _ctl[f.name] = TextEditingController(text: v);
      }
    }
  }

  @override
  void dispose() {
    for (final c in _ctl.values) {
      c.dispose();
    }
    super.dispose();
  }

  void _set(String name, String value) => _values[name] = value;

  Future<void> _pickPhoto(ImageSource source) async {
    try {
      final x = await ImagePicker().pickImage(source: source, maxWidth: 2400, maxHeight: 2400, imageQuality: 85);
      if (x == null) return;
      var path = x.path;
      if (sniffImage(path) == null) {
        setState(() => _error = 'Please choose a PNG, JPG or WEBP photo.');
        return;
      }
      if (File(path).lengthSync() > AppConfig.maxImageBytes) {
        // too big: shrink instead of making the person try again
        final out = '${path}_small.jpg';
        path = await shrinkToJpeg(path, out);
      }
      if (File(path).lengthSync() > AppConfig.maxImageBytes) {
        setState(() => _error = 'The photo must be 5 MB or smaller.');
        return;
      }
      setState(() {
        _photo = File(path);
        _error = '';
        _invalid.remove('image');
      });
    } catch (_) {
      setState(() => _error = 'The photo could not be opened.');
    }
  }

  Future<void> _submit() async {
    final missing = <String>{};
    final fields = <String, String>{};
    for (final f in spec.fields) {
      if (f.type == FieldType.file) continue;
      final value = (_values[f.name] ?? '').trim();
      if (f.required && value.isEmpty) missing.add(f.name);
      fields[f.name] = value;
      if (f.type == FieldType.select && value == 'Other') {
        final typed = (_values['${f.name}_other'] ?? '').trim();
        if (typed.isEmpty) missing.add('${f.name}_other');
        fields['${f.name}_other'] = typed;
      }
    }
    setState(() => _invalid
      ..clear()
      ..addAll(missing));
    if (missing.isNotEmpty) {
      setState(() => _error = 'Please complete all required fields.');
      return;
    }
    setState(() {
      _error = '';
      _busy = true;
    });
    try {
      final form = await api.buildForm(fields,
          files: {'image': _photo == null ? null : toUpload(_photo!, 'photo')});
      final result = await api.postForm(spec.endpoint, form);
      setState(() => _done = true);
      widget.onSuccess?.call(result);
    } on ApiError catch (e) {
      setState(() {
        _error = e.message;
        _busy = false;
      });
    }
  }

  InputDecoration _deco(FieldSpec f) => InputDecoration(
        labelText: '${f.label}${f.required ? ' *' : ''}',
        hintText: f.hint,
        errorText: _invalid.contains(f.name) ? 'Required' : null,
        floatingLabelBehavior: FloatingLabelBehavior.always,
      );

  Widget _field(FieldSpec f) {
    switch (f.type) {
      case FieldType.textarea:
        return TextField(
          controller: _ctl[f.name],
          enabled: !_done,
          minLines: 3,
          maxLines: 6,
          decoration: _deco(f),
          onChanged: (v) => _set(f.name, v),
        );
      case FieldType.select:
        final current = _values[f.name] ?? '';
        return Column(children: [
          DropdownButtonFormField<String>(
            value: f.options.contains(current) ? current : null,
            isExpanded: true,
            decoration: _deco(f).copyWith(hintText: 'Choose...'),
            items: f.options.map((o) => DropdownMenuItem(value: o, child: Text(o))).toList(),
            onChanged: _done ? null : (v) => setState(() => _set(f.name, v ?? '')),
          ),
          if (current == 'Other')
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: TextFormField(
                initialValue: _values['${f.name}_other'] ?? '',
                enabled: !_done,
                maxLength: 50,
                decoration: InputDecoration(
                  hintText: 'Type your ${f.label.toLowerCase()} *',
                  counterText: '',
                  errorText: _invalid.contains('${f.name}_other') ? 'Required' : null,
                ),
                onChanged: (v) => _set('${f.name}_other', v),
              ),
            ),
        ]);
      case FieldType.date:
        return TextField(
          controller: _ctl[f.name],
          readOnly: true,
          enabled: !_done,
          decoration: _deco(f).copyWith(suffixIcon: const Icon(Icons.calendar_today_outlined, size: 20)),
          onTap: () async {
            final lim = _dateLimits(widget.kind, f);
            var initial = DateTime.tryParse(_values[f.name] ?? '') ?? _today();
            if (initial.isBefore(lim.first)) initial = lim.first;
            if (initial.isAfter(lim.last)) initial = lim.last;
            final picked = await showDatePicker(
                context: context, initialDate: initial, firstDate: lim.first, lastDate: lim.last);
            if (picked != null) {
              _ctl[f.name]!.text = isoDate(picked);
              setState(() => _set(f.name, isoDate(picked)));
            }
          },
        );
      case FieldType.time:
        return TextField(
          controller: _ctl[f.name],
          readOnly: true,
          enabled: !_done,
          decoration: _deco(f).copyWith(suffixIcon: const Icon(Icons.access_time, size: 20)),
          onTap: () async {
            final picked = await showTimePicker(context: context, initialTime: TimeOfDay.now());
            if (picked != null) {
              final v = '${two(picked.hour)}:${two(picked.minute)}'; // 24h "HH:MM" like <input type=time>
              _ctl[f.name]!.text = v;
              setState(() => _set(f.name, v));
            }
          },
        );
      case FieldType.file:
        return _photoPicker(f);
      case FieldType.text:
        if (f.list) {
          final facilities = context.read<AuthState>().facilities;
          return Autocomplete<String>(
            optionsBuilder: (v) => v.text.isEmpty
                ? facilities
                : facilities.where((n) => n.toLowerCase().contains(v.text.toLowerCase())),
            onSelected: (v) => _set(f.name, v),
            fieldViewBuilder: (context, controller, focus, onSubmit) => TextField(
              controller: controller,
              focusNode: focus,
              enabled: !_done,
              decoration: _deco(f),
              onChanged: (v) => _set(f.name, v),
            ),
          );
        }
        return TextField(
          controller: _ctl[f.name],
          enabled: !_done,
          decoration: _deco(f),
          onChanged: (v) => _set(f.name, v),
        );
    }
  }

  Widget _photoPicker(FieldSpec f) {
    final photo = _photo;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(f.label, style: const TextStyle(color: C.muted, fontSize: 13)),
      const SizedBox(height: 8),
      if (photo != null)
        Stack(children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(10),
            child: Image.file(photo, height: 150, width: double.infinity, fit: BoxFit.cover),
          ),
          Positioned(
            right: 6,
            top: 6,
            child: CircleAvatar(
              radius: 16,
              backgroundColor: Colors.black54,
              child: IconButton(
                padding: EdgeInsets.zero,
                iconSize: 18,
                color: Colors.white,
                onPressed: _done ? null : () => setState(() => _photo = null),
                icon: const Icon(Icons.close),
              ),
            ),
          ),
        ])
      else
        Row(children: [
          Expanded(
            child: OutlinedButton.icon(
              onPressed: _done ? null : () => _pickPhoto(ImageSource.camera),
              icon: const Icon(Icons.photo_camera_outlined, size: 20),
              label: const Text('Take photo'),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: OutlinedButton.icon(
              onPressed: _done ? null : () => _pickPhoto(ImageSource.gallery),
              icon: const Icon(Icons.image_outlined, size: 20),
              label: const Text('Upload'),
            ),
          ),
        ]),
    ]);
  }

  @override
  Widget build(BuildContext context) {
    final user = context.watch<AuthState>().user;
    final body = <Widget>[];
    for (var i = 0; i < spec.fields.length; i++) {
      final f = spec.fields[i];
      final next = i + 1 < spec.fields.length ? spec.fields[i + 1] : null;
      // two time pickers share one row
      if (f.type == FieldType.time && next != null && next.type == FieldType.time) {
        body.add(Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(child: _field(f)),
          const SizedBox(width: 10),
          Expanded(child: _field(next)),
        ]));
        i++;
      } else {
        body.add(_field(f));
      }
      body.add(const SizedBox(height: 14));
    }

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(spec.title, style: const TextStyle(fontFamily: serif, fontSize: 20, fontWeight: FontWeight.w700, color: C.blueDeep)),
      const SizedBox(height: 4),
      Text(spec.desc, style: const TextStyle(color: C.muted, fontSize: 13.5)),
      const SizedBox(height: 14),
      TextFormField(
        readOnly: true,
        initialValue: user == null ? '' : '${user.name} (${user.email})',
        decoration: const InputDecoration(labelText: 'Signed in as', floatingLabelBehavior: FloatingLabelBehavior.always),
      ),
      const SizedBox(height: 14),
      ...body,
      if (_error.isNotEmpty) Message(_error, isError: true),
      SizedBox(
        width: double.infinity,
        child: FilledButton(
          onPressed: (_busy || _done) ? null : _submit,
          child: Text(_done ? 'Submitted' : (_busy ? 'Submitting...' : 'Submit')),
        ),
      ),
    ]);
  }
}
