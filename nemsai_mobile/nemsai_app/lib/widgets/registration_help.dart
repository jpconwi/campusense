import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../theme.dart';
import 'common.dart';

/// "Need help? Send a message to an admin" (POST /api/auth/help-messages, no sign-in needed).
class RegistrationHelp extends StatefulWidget {
  const RegistrationHelp({super.key, this.name = '', this.email = '', this.applicantType = 'student'});
  final String name;
  final String email;
  final String applicantType;

  @override
  State<RegistrationHelp> createState() => _RegistrationHelpState();
}

class _RegistrationHelpState extends State<RegistrationHelp> {
  late final _name = TextEditingController(text: widget.name);
  late final _email = TextEditingController(text: widget.email);
  final _message = TextEditingController();
  late String _type = widget.applicantType == 'instructor' ? 'instructor' : 'student';
  String _category = 'Registration';
  bool _busy = false;
  String _error = '';
  String _notice = '';

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _message.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    if (_name.text.trim().isEmpty || !_email.text.contains('@') || _message.text.trim().isEmpty) {
      setState(() {
        _notice = '';
        _error = 'Please fill in your name, a valid email and your message.';
      });
      return;
    }
    setState(() {
      _busy = true;
      _error = '';
      _notice = '';
    });
    try {
      final r = await api.post('/api/auth/help-messages', json: {
        'name': _name.text.trim(),
        'email': _email.text.trim(),
        'applicant_type': _type,
        'category': _category,
        'message': _message.text.trim(),
      });
      _message.clear();
      setState(() => _notice = (r['message'] ?? 'Your message was sent to the admin inbox.') as String);
    } on ApiError catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
      child: ExpansionTile(
        tilePadding: EdgeInsets.zero,
        childrenPadding: const EdgeInsets.only(bottom: 8),
        title: const Text('Need help? Send a message to an admin',
            style: TextStyle(color: C.blue, fontWeight: FontWeight.w600, fontSize: 14.5)),
        children: [
          TextField(controller: _name, maxLength: 120, decoration: const InputDecoration(labelText: 'Name', counterText: '')),
          const SizedBox(height: 10),
          TextField(
              controller: _email,
              maxLength: 255,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(labelText: 'Email for reply', counterText: '')),
          const SizedBox(height: 10),
          DropdownButtonFormField<String>(
            value: _type,
            decoration: const InputDecoration(labelText: 'Account type'),
            items: const [
              DropdownMenuItem(value: 'student', child: Text('Student')),
              DropdownMenuItem(value: 'instructor', child: Text('Instructor')),
            ],
            onChanged: (v) => setState(() => _type = v ?? 'student'),
          ),
          const SizedBox(height: 10),
          DropdownButtonFormField<String>(
            value: _category,
            decoration: const InputDecoration(labelText: 'Help topic'),
            items: const ['Registration', 'Login or access', 'Account deletion', 'Other']
                .map((e) => DropdownMenuItem(value: e, child: Text(e)))
                .toList(),
            onChanged: (v) => setState(() => _category = v ?? 'Registration'),
          ),
          const SizedBox(height: 10),
          TextField(
              controller: _message,
              maxLength: 2000,
              minLines: 3,
              maxLines: 6,
              decoration: const InputDecoration(labelText: 'How can we help?')),
          if (_error.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 6), child: Message(_error, isError: true)),
          if (_notice.isNotEmpty) Padding(padding: const EdgeInsets.only(top: 6), child: Message(_notice, isOk: true)),
          const SizedBox(height: 6),
          SizedBox(
            width: double.infinity,
            child: FilledButton(onPressed: _busy ? null : _send, child: Text(_busy ? 'Sending...' : 'Send message')),
          ),
          const SizedBox(height: 6),
          const Text('An administrator can review your message and reply to the email you provide.',
              style: TextStyle(color: C.muted, fontSize: 12.5)),
        ],
      ),
    );
  }
}
