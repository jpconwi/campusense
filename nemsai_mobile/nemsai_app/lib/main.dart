import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'api/auth_state.dart';
import 'screens/admin_notice_screen.dart';
import 'screens/home_screen.dart';
import 'screens/login_screen.dart';
import 'screens/register_screen.dart';
import 'screens/role_select_screen.dart';
import 'theme.dart';
import 'widgets/skeleton.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SystemChrome.setPreferredOrientations(const [DeviceOrientation.portraitUp]);
  runApp(
    ChangeNotifierProvider(
      create: (_) => AuthState()..boot(),
      child: const NemsaiApp(),
    ),
  );
}

class NemsaiApp extends StatelessWidget {
  const NemsaiApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'NEMSAI',
        debugShowCheckedModeBanner: false,
        navigatorKey: navigatorKey,
        theme: buildTheme(),
        home: const AuthGate(),
      );
}

/// Picks the first screen from the sign-in state (like the route guards in the website's App.jsx).
class AuthGate extends StatelessWidget {
  const AuthGate({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    if (auth.loading) return const LaunchSkeleton();
    final user = auth.user;
    if (user == null) {
      return auth.pending != null ? const RegisterScreen() : const LoginScreen();
    }
    if (user.role == null) return const RoleSelectScreen();
    if (user.role == 'admin') return const AdminNoticeScreen();
    return const HomeScreen();
  }
}
