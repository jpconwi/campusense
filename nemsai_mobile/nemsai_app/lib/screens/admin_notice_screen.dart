import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/auth_state.dart';
import '../theme.dart';
import '../widgets/common.dart';

/// Administrators use the website; this app is for students and instructors.
class AdminNoticeScreen extends StatelessWidget {
  const AdminNoticeScreen({super.key});
  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('NEMSAI')),
        body: Padding(
          padding: const EdgeInsets.all(20),
          child: Center(
            child: Panel(
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                const AppLogo(size: 64),
                const SizedBox(height: 12),
                const Text('Administrator account',
                    style: TextStyle(fontFamily: serif, fontSize: 21, fontWeight: FontWeight.w700, color: C.blueDeep)),
                const SizedBox(height: 8),
                const Text('The admin dashboard is on the NEMSAI website. This app is for students and instructors.',
                    textAlign: TextAlign.center, style: TextStyle(color: C.muted)),
                const SizedBox(height: 16),
                FilledButton(onPressed: () => context.read<AuthState>().logout(), child: const Text('Sign out')),
              ]),
            ),
          ),
        ),
      );
}
