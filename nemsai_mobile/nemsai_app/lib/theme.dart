import 'package:flutter/material.dart';

/// Colours copied from the website's app.css.
class C {
  static const blue = Color(0xFF17119E);
  static const blueDeep = Color(0xFF0D0A66);
  static const blueSoft = Color(0xFFECEBFF);
  static const gold = Color(0xFFF2B705);
  static const paper = Color(0xFFF4F5FB);
  static const line = Color(0xFFD8DAF0);
  static const ink = Color(0xFF15163A);
  static const muted = Color(0xFF5B5D82);
  static const error = Color(0xFFB3121C);
  static const okBg = Color(0xFFEEF8EF);
  static const okLine = Color(0xFFB8DCB9);
  static const skBase = Color(0xFFE6E8F5);
  static const skHigh = Color(0xFFF7F8FD);
}

const serif = 'serif';

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(seedColor: C.blue, primary: C.blue, secondary: C.gold);
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: C.paper,
    appBarTheme: const AppBarTheme(
      backgroundColor: C.blue,
      foregroundColor: Colors.white,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: TextStyle(fontFamily: serif, fontSize: 19, fontWeight: FontWeight.w700, color: Colors.white),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: const BorderSide(color: C.line)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: const BorderSide(color: C.line)),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: const BorderSide(color: C.blue, width: 1.6)),
      errorBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: const BorderSide(color: C.error)),
      focusedErrorBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: const BorderSide(color: C.error, width: 1.6)),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: C.blue,
        foregroundColor: Colors.white,
        minimumSize: const Size(0, 48),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: C.blue,
        minimumSize: const Size(0, 48),
        side: const BorderSide(color: C.line),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
      ),
    ),
  );
}
