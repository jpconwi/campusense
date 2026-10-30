/// common.dart - small shared pieces: scaffold with menu, panels, badges, empty states, messages.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/api_client.dart';
import '../api/auth_state.dart';
import '../screens/chat_screen.dart';
import '../screens/faculty_screen.dart';
import '../screens/home_screen.dart';
import '../screens/my_list_screen.dart';
import '../screens/profile_screen.dart';
import '../theme.dart';

/// White rounded box with a thin border (the website's .card).
class Panel extends StatelessWidget {
  const Panel({super.key, required this.child, this.padding = const EdgeInsets.all(16), this.color = Colors.white});
  final Widget child;
  final EdgeInsets padding;
  final Color color;
  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        padding: padding,
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: C.line),
        ),
        child: child,
      );
}

class AppLogo extends StatelessWidget {
  const AppLogo({super.key, this.size = 48});
  final double size;
  @override
  Widget build(BuildContext context) => Image.asset('assets/logo.png', width: size, height: size);
}

class PageTitle extends StatelessWidget {
  const PageTitle(this.title, {super.key, this.intro});
  final String title;
  final String? intro;
  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title,
              style: const TextStyle(fontFamily: serif, fontSize: 25, fontWeight: FontWeight.w700, color: C.blueDeep)),
          if (intro != null) ...[
            const SizedBox(height: 6),
            Text(intro!, style: const TextStyle(color: C.muted, height: 1.4)),
          ],
          const SizedBox(height: 14),
        ],
      );
}

class Message extends StatelessWidget {
  const Message(this.text, {super.key, this.isError = false, this.isOk = false});
  final String text;
  final bool isError;
  final bool isOk;
  @override
  Widget build(BuildContext context) {
    final color = isError ? C.error : (isOk ? const Color(0xFF2E7D32) : C.blue);
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: isOk ? C.okBg : Colors.white,
        borderRadius: BorderRadius.circular(8),
        border: Border(left: BorderSide(color: color, width: 4), top: const BorderSide(color: C.line), right: const BorderSide(color: C.line), bottom: const BorderSide(color: C.line)),
      ),
      child: Text(text, style: TextStyle(color: isError ? C.error : C.ink)),
    );
  }
}

class EmptyState extends StatelessWidget {
  const EmptyState({super.key, required this.title, this.text, this.icon = Icons.inbox_outlined, this.action});
  final String title;
  final String? text;
  final IconData icon;
  final Widget? action;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 30, horizontal: 16),
        child: Column(children: [
          CircleAvatar(radius: 28, backgroundColor: C.blueSoft, child: Icon(icon, color: C.blue, size: 28)),
          const SizedBox(height: 12),
          Text(title, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16, color: C.blueDeep)),
          if (text != null) ...[
            const SizedBox(height: 4),
            Text(text!, textAlign: TextAlign.center, style: const TextStyle(color: C.muted)),
          ],
          if (action != null) ...[const SizedBox(height: 14), action!],
        ]),
      );
}

/// Coloured pill for a record status (Pending, Approved, ...).
class StatusBadge extends StatelessWidget {
  const StatusBadge(this.status, {super.key});
  final String status;
  @override
  Widget build(BuildContext context) {
    final s = status.toLowerCase();
    Color bg = C.blueSoft, fg = C.blue;
    if (s.contains('pending') || s.contains('review') || s.contains('absent')) {
      bg = const Color(0xFFFFF3CD);
      fg = const Color(0xFF8A6100);
    } else if (s.contains('approved') || s.contains('resolved') || s.contains('done') ||
        s.contains('complete') || s.contains('available') || s.contains('closed')) {
      bg = const Color(0xFFDFF3E1);
      fg = const Color(0xFF1E6B2A);
    } else if (s.contains('reject') || s.contains('denied') || s.contains('cancel') || s.contains('declin')) {
      bg = const Color(0xFFFBE0E2);
      fg = C.error;
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(999)),
      child: Text(status, style: TextStyle(color: fg, fontWeight: FontWeight.w700, fontSize: 12)),
    );
  }
}

/// Shown on top of every signed-in screen when the (free-tier) server is slow to answer.
class SlowServerBanner extends StatelessWidget {
  const SlowServerBanner({super.key});
  @override
  Widget build(BuildContext context) => ValueListenableBuilder<bool>(
        valueListenable: api.slow,
        builder: (context, slow, _) => AnimatedSize(
          duration: const Duration(milliseconds: 200),
          child: slow
              ? Container(
                  width: double.infinity,
                  color: const Color(0xFFFFF3CD),
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  child: const Row(children: [
                    SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2)),
                    SizedBox(width: 10),
                    Expanded(
                      child: Text('Waking up the server - the first request can take up to a minute.',
                          style: TextStyle(fontSize: 13, color: Color(0xFF5C4400))),
                    ),
                  ]),
                )
              : const SizedBox(width: double.infinity),
        ),
      );
}

typedef _Dest = ({String label, IconData icon, Widget Function() page});

Map<String, _Dest> _destinations() => {
      '/': (label: 'Home', icon: Icons.home_outlined, page: () => const HomeScreen()),
      '/ai': (label: 'Campus AI', icon: Icons.chat_bubble_outline, page: () => const ChatScreen()),
      '/reports': (label: 'My Reports', icon: Icons.description_outlined, page: () => const MyListScreen(kind: 'reports')),
      '/concerns': (label: 'My Concerns', icon: Icons.warning_amber_rounded, page: () => const MyListScreen(kind: 'concerns')),
      '/feedback': (label: 'Feedback', icon: Icons.rate_review_outlined, page: () => const MyListScreen(kind: 'feedback')),
      '/reservations': (label: 'Reservations', icon: Icons.event_available_outlined, page: () => const MyListScreen(kind: 'reservations')),
      '/faculty': (label: 'Faculty Availability', icon: Icons.school_outlined, page: () => const FacultyScreen()),
      '/profile': (label: 'Profile', icon: Icons.person_outline, page: () => const ProfileScreen()),
    };

/// Same menu items the website shows for each role (see NAV in backend security.py).
List<String> navFor(String? role) => [
      '/', '/ai', '/reports', '/concerns', '/feedback',
      if (role == 'instructor') '/faculty',
      if (role == 'instructor') '/reservations',
      '/profile',
    ];

/// Move to a menu destination while keeping Home at the bottom of the stack.
void goTo(BuildContext context, String path) {
  final dest = _destinations()[path];
  final nav = Navigator.of(context);
  if (dest == null || path == '/') {
    nav.popUntil((r) => r.isFirst);
    return;
  }
  nav.pushAndRemoveUntil(MaterialPageRoute<void>(builder: (_) => dest.page()), (r) => r.isFirst);
}

class AppScaffold extends StatelessWidget {
  const AppScaffold({
    super.key,
    required this.title,
    required this.body,
    required this.current,
    this.actions,
    this.resizeForKeyboard = true,
  });
  final String title;
  final Widget body;
  final String current; // path of this screen, to highlight it in the menu
  final List<Widget>? actions;
  final bool resizeForKeyboard;

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    final user = auth.user;
    final dests = _destinations();
    return Scaffold(
      resizeToAvoidBottomInset: resizeForKeyboard,
      appBar: AppBar(title: Text(title), actions: actions),
      drawer: Drawer(
        backgroundColor: C.blueDeep,
        child: SafeArea(
          child: Column(children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
              child: Row(children: [
                const AppLogo(size: 44),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    const Text('NEMSAI',
                        style: TextStyle(color: Colors.white, fontFamily: serif, fontWeight: FontWeight.w700, fontSize: 18)),
                    Text(user?.role == null ? '' : '${user!.role![0].toUpperCase()}${user.role!.substring(1)}',
                        style: const TextStyle(color: C.gold, fontSize: 13)),
                  ]),
                ),
              ]),
            ),
            if (user != null)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Text('${user.name}\n${user.email}',
                      style: const TextStyle(color: Color(0xFFCFD0FF), fontSize: 12.5, height: 1.35)),
                ),
              ),
            const Divider(color: Colors.white24, height: 1),
            Expanded(
              child: ListView(padding: const EdgeInsets.symmetric(vertical: 8), children: [
                for (final path in navFor(user?.role))
                  if (dests[path] != null)
                    ListTile(
                      leading: Icon(dests[path]!.icon, color: path == current ? C.gold : const Color(0xFFCFD0FF)),
                      title: Text(dests[path]!.label,
                          style: TextStyle(
                              color: path == current ? Colors.white : const Color(0xFFCFD0FF),
                              fontWeight: path == current ? FontWeight.w700 : FontWeight.w500)),
                      selected: path == current,
                      selectedTileColor: Colors.white10,
                      onTap: () {
                        Navigator.of(context).pop(); // close the drawer
                        if (path != current) goTo(context, path);
                      },
                    ),
              ]),
            ),
            const Divider(color: Colors.white24, height: 1),
            ListTile(
              leading: const Icon(Icons.logout, color: Color(0xFFCFD0FF)),
              title: const Text('Sign out', style: TextStyle(color: Color(0xFFCFD0FF))),
              onTap: () async {
                Navigator.of(context).pop();
                await context.read<AuthState>().logout();
              },
            ),
          ]),
        ),
      ),
      body: Column(children: [
        const SlowServerBanner(),
        Expanded(child: body),
      ]),
    );
  }
}

String slug(Object? v) => '$v'.toLowerCase().replaceAll(' ', '-');
String padId(Object? id) => '$id'.padLeft(4, '0');

String two(int n) => n.toString().padLeft(2, '0');
String isoDate(DateTime d) => '${d.year}-${two(d.month)}-${two(d.day)}';
String clock(DateTime d) {
  final h = d.hour % 12 == 0 ? 12 : d.hour % 12;
  return '$h:${two(d.minute)} ${d.hour < 12 ? 'AM' : 'PM'}';
}
