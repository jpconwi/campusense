import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/auth_state.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/registration_help.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  bool _busy = false;
  String _error = '';

  Future<void> _go() async {
    final auth = context.read<AuthState>();
    auth.clearFlash();
    setState(() {
      _busy = true;
      _error = '';
    });
    final err = await auth.continueWithGoogle();
    if (mounted) {
      setState(() {
        _busy = false;
        _error = err ?? '';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final flash = context.watch<AuthState>().flash;
    return Scaffold(
      body: Column(children: [
        // header band like the website
        Container(
          width: double.infinity,
          decoration: const BoxDecoration(
            color: C.blue,
            border: Border(bottom: BorderSide(color: C.gold, width: 4)),
          ),
          child: SafeArea(
            bottom: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(18, 10, 18, 12),
              child: Row(children: const [
                AppLogo(size: 44),
                SizedBox(width: 12),
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('NEMSAI', style: TextStyle(color: Colors.white, fontFamily: serif, fontWeight: FontWeight.w700, fontSize: 21)),
                  Text('NEMSU Tandag Main Campus Assistant', style: TextStyle(color: Color(0xFFD7D9FF), fontSize: 12.5)),
                ]),
              ]),
            ),
          ),
        ),
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(18),
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 460),
                child: Panel(
                  padding: const EdgeInsets.all(22),
                  child: Column(children: [
                    const AppLogo(size: 84),
                    const SizedBox(height: 10),
                    const Text('NEMSAI',
                        style: TextStyle(fontFamily: serif, fontSize: 28, fontWeight: FontWeight.w700, color: C.blueDeep)),
                    const SizedBox(height: 4),
                    const Text('NEMSU Tandag Main Campus Assistant', style: TextStyle(color: C.muted)),
                    const SizedBox(height: 18),
                    if (_error.isNotEmpty) Message(_error, isError: true),
                    if (_error.isEmpty && flash != null) Message(flash.text, isError: flash.isError),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton(
                        style: OutlinedButton.styleFrom(
                          backgroundColor: Colors.white,
                          foregroundColor: C.ink,
                          minimumSize: const Size(0, 52),
                        ),
                        onPressed: _busy ? null : _go,
                        child: _busy
                            ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.4))
                            : Row(mainAxisAlignment: MainAxisAlignment.center, children: const [
                                Text('G',
                                    style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: Color(0xFF4285F4))),
                                SizedBox(width: 12),
                                Text('Continue with Google'),
                              ]),
                      ),
                    ),
                    const SizedBox(height: 16),
                    const Text(
                      'Continue with your NEMSU Google account for automatic account setup. If you use personal '
                      'Gmail, choose Student or Instructor and submit the requested details for admin approval.\n'
                      'Google handles sign-in; this app never sees your Google password.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: C.muted, fontSize: 13, height: 1.45),
                    ),
                    const SizedBox(height: 8),
                    const RegistrationHelp(),
                  ]),
                ),
              ),
            ),
          ),
        ),
      ]),
    );
  }
}
