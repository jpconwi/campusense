import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/auth_state.dart';
import '../theme.dart';
import '../widgets/common.dart';

class RoleSelectScreen extends StatefulWidget {
  const RoleSelectScreen({super.key});
  @override
  State<RoleSelectScreen> createState() => _RoleSelectScreenState();
}

class _RoleSelectScreenState extends State<RoleSelectScreen> {
  String _error = '';
  String? _busyRole;

  Future<void> _choose(String role) async {
    setState(() {
      _busyRole = role;
      _error = '';
    });
    final err = await context.read<AuthState>().chooseRole(role);
    if (mounted) {
      setState(() {
        _busyRole = null;
        _error = err ?? '';
      });
    }
  }

  Widget _card(String role, String title, String text) => Panel(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title, style: const TextStyle(fontFamily: serif, fontSize: 19, fontWeight: FontWeight.w700, color: C.blueDeep)),
          const SizedBox(height: 4),
          Text(text, style: const TextStyle(color: C.muted)),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: _busyRole == null ? () => _choose(role) : null,
              child: Text(_busyRole == role ? 'Please wait...' : 'Continue'),
            ),
          ),
        ]),
      );

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    return Scaffold(
      appBar: AppBar(title: const Text('Select your account type')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        Text('Welcome, ${auth.user?.name ?? ''}. Choose one to continue.', style: const TextStyle(color: C.muted)),
        const SizedBox(height: 14),
        if (_error.isNotEmpty) Message(_error, isError: true),
        _card('student', 'Student', 'Ask campus questions, report concerns and give feedback.'),
        const SizedBox(height: 12),
        _card('instructor', 'Instructor',
            'Everything students can do, plus room reservations, faculty availability and absence reports.'),
        const SizedBox(height: 12),
        OutlinedButton(onPressed: () => auth.logout(), child: const Text('Use a different account')),
      ]),
    );
  }
}
