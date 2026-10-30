import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/auth_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/registration_help.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  Widget _row(String k, Widget v) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(width: 110, child: Text(k, style: const TextStyle(color: C.muted, fontWeight: FontWeight.w600))),
          Expanded(child: v),
        ]),
      );

  @override
  Widget build(BuildContext context) {
    final user = context.watch<AuthState>().user!;
    return AppScaffold(
      title: 'Profile',
      current: '/profile',
      body: ListView(padding: const EdgeInsets.all(16), children: [
        const PageTitle('Profile', intro: 'Your details come from your Google account.'),
        Panel(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            _row('Name', Text(user.name)),
            const Divider(height: 1, color: C.line),
            _row('Email', Text(user.email)),
            const Divider(height: 1, color: C.line),
            _row(
              'Account type',
              Align(
                alignment: Alignment.centerLeft,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
                  decoration: BoxDecoration(color: C.gold, borderRadius: BorderRadius.circular(999)),
                  child: Text((user.role ?? '').toUpperCase(),
                      style: const TextStyle(color: C.blueDeep, fontWeight: FontWeight.w800, fontSize: 12)),
                ),
              ),
            ),
            const Divider(height: 1, color: C.line),
            _row('Member since', Text(user.createdAt)),
            const Divider(height: 1, color: C.line),
            _row('Last login', Text(user.lastLogin)),
            const SizedBox(height: 10),
            const Text('Need a different account type? Ask an administrator to change it.',
                style: TextStyle(color: C.muted, fontSize: 13)),
          ]),
        ),
        const SizedBox(height: 14),
        Panel(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('Help messages',
                style: TextStyle(fontFamily: serif, fontSize: 18, fontWeight: FontWeight.w700, color: C.blueDeep)),
            const SizedBox(height: 4),
            const Text('Ask about account access, registration, account deletion, or another issue. An admin can reply to your email.',
                style: TextStyle(color: C.muted, fontSize: 13.5)),
            RegistrationHelp(name: user.name, email: user.email, applicantType: user.role ?? 'student'),
          ]),
        ),
        const SizedBox(height: 14),
        OutlinedButton.icon(
          onPressed: () => context.read<AuthState>().logout(),
          icon: const Icon(Icons.logout),
          label: const Text('Sign out'),
        ),
      ]),
    );
  }
}
