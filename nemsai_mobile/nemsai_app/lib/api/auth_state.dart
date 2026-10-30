/// auth_state.dart - who is signed in (loaded from GET /api/auth/me), Google sign-in, flash messages.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:google_sign_in/google_sign_in.dart';

import '../config.dart';
import 'api_client.dart';

final navigatorKey = GlobalKey<NavigatorState>();

class AppUser {
  AppUser({
    required this.id,
    required this.name,
    required this.email,
    required this.role,
    required this.createdAt,
    required this.lastLogin,
  });

  final int id;
  final String name;
  final String email;
  final String? role; // student / instructor / admin / null (not chosen yet)
  final String createdAt;
  final String lastLogin;

  bool get isInstructor => role == 'instructor';
  String get firstName => name.trim().isEmpty ? '' : name.trim().split(RegExp(r'\s+')).first;

  factory AppUser.fromJson(Map<String, dynamic> j) => AppUser(
        id: (j['id'] as num?)?.toInt() ?? 0,
        name: (j['name'] ?? '') as String,
        email: (j['email'] ?? '') as String,
        role: j['role'] as String?,
        createdAt: (j['created_at'] ?? '') as String,
        lastLogin: (j['last_login'] ?? '') as String,
      );
}

/// Personal-Gmail person who still has to register (student / instructor form).
class PendingRegistration {
  PendingRegistration(this.email, this.googleName);
  final String email;
  final String googleName;
}

class Flash {
  Flash(this.text, {this.isError = false});
  final String text;
  final bool isError;
}

class AuthState extends ChangeNotifier {
  AuthState() {
    api.onUnauthorized = _sessionEnded;
  }

  static const _tokenKey = 'nemsai_token';
  final _storage = const FlutterSecureStorage();
  final _google = GoogleSignIn(
    scopes: const ['email', 'profile'],
    serverClientId: AppConfig.googleServerClientId,
  );

  bool loading = true;
  AppUser? user;
  List<String> facilities = const [];
  PendingRegistration? pending;
  Flash? flash;

  void setFlash(String text, {bool isError = false}) {
    flash = Flash(text, isError: isError);
    notifyListeners();
  }

  void clearFlash() {
    if (flash != null) {
      flash = null;
      notifyListeners();
    }
  }

  // ------------------------------------------------------------------ start-up
  Future<void> boot() async {
    try {
      api.token = await _storage.read(key: _tokenKey);
    } catch (_) {
      api.token = null; // keystore problem: just ask the person to sign in again
    }
    if (api.token == null) {
      loading = false;
      notifyListeners();
      return;
    }
    await refresh();
  }

  Future<AppUser?> refresh() async {
    try {
      final d = await api.get('/api/auth/me');
      final u = d['user'];
      user = u is Map ? AppUser.fromJson(Map<String, dynamic>.from(u)) : null;
      facilities = ((d['facilities'] as List?) ?? const []).map((e) => e.toString()).toList();
      if (user == null) await _forgetToken();
    } on ApiError catch (e) {
      // 401 -> signed out (handled by _sessionEnded). Network problem on start-up: keep the token
      // but show the sign-in page with a message so the person can retry.
      if (e.status == null) {
        user = null;
        flash = Flash(e.message, isError: true);
      } else {
        user = null;
        await _forgetToken();
      }
    }
    loading = false;
    notifyListeners();
    return user;
  }

  Future<void> _forgetToken() async {
    api.token = null;
    try {
      await _storage.delete(key: _tokenKey);
    } catch (_) {}
  }

  void _sessionEnded() {
    if (user == null) return;
    user = null;
    _forgetToken();
    flash = Flash('Your session ended. Please sign in again.', isError: true);
    navigatorKey.currentState?.popUntil((r) => r.isFirst);
    notifyListeners();
  }

  // ------------------------------------------------------------- Google sign-in
  Future<GoogleSignInAccount?> _pickAccount() async {
    try {
      await _google.signOut(); // always show the account chooser
    } catch (_) {}
    return _google.signIn();
  }

  /// "Continue with Google". Returns an error message, or null when the flow moved on
  /// (signed in, role selection needed, or registration form needed).
  Future<String?> continueWithGoogle() async {
    try {
      final account = await _pickAccount();
      if (account == null) return 'Google sign-in was cancelled. Please try again.';
      final auth = await account.authentication;
      final idToken = auth.idToken;
      if (idToken == null || idToken.isEmpty) {
        return 'Google did not return an ID token. Please try again.';
      }
      final d = await api.post('/api/auth/mobile/google',
          json: {'id_token': idToken, 'purpose': 'register'});

      if (d['status'] == 'registration_required') {
        pending = PendingRegistration(
            (d['email'] ?? account.email) as String, (d['google_name'] ?? account.displayName ?? '') as String);
        flash = null;
        notifyListeners();
        return null;
      }
      final token = d['token'] as String?;
      if (token == null) return 'Sign-in failed. Please try again.';
      api.token = token;
      try {
        await _storage.write(key: _tokenKey, value: token);
      } catch (_) {}
      pending = null;
      flash = null;
      await refresh();
      return user == null ? 'Sign-in failed. Please try again.' : null;
    } on PlatformException catch (e) {
      return _googleErrorText(e);
    } on ApiError catch (e) {
      return e.message;
    }
  }

  String _googleErrorText(PlatformException e) {
    final c = '${e.code} ${e.message}';
    if (c.contains('sign_in_canceled') || c.contains('12501')) {
      return 'Google sign-in was cancelled. Please try again.';
    }
    if (c.contains('network_error') || c.contains('7:')) {
      return 'No internet connection. Please check your network.';
    }
    if (c.contains('10') || c.contains('12500') || c.contains('DEVELOPER_ERROR')) {
      return 'Google sign-in is not set up for this build yet (OAuth client / SHA-1 mismatch). '
          'Please contact the administrator.';
    }
    return 'Google sign-in failed. Please try again.';
  }

  /// A fresh Google ID token for the registration request (the first one may have expired).
  Future<String?> freshIdToken() async {
    GoogleSignInAccount? acc = _google.currentUser;
    try {
      acc = await _google.signInSilently() ?? acc;
    } catch (_) {}
    final auth = await acc?.authentication;
    return auth?.idToken;
  }

  void cancelRegistration() {
    pending = null;
    notifyListeners();
  }

  // ------------------------------------------------------------------- role / out
  Future<String?> chooseRole(String role) async {
    try {
      await api.post('/api/auth/role', json: {'role': role});
      await refresh();
      return null;
    } on ApiError catch (e) {
      return e.message;
    }
  }

  Future<void> logout() async {
    try {
      await api.post('/api/auth/logout');
    } catch (_) {}
    try {
      await _google.signOut();
    } catch (_) {}
    await _forgetToken();
    user = null;
    pending = null;
    flash = Flash('You have been signed out.');
    navigatorKey.currentState?.popUntil((r) => r.isFirst);
    notifyListeners();
  }
}
