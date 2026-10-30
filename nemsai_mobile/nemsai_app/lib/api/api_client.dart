/// api_client.dart - the only place that talks to the FastAPI backend.
///
/// Auth: every request sends `Authorization: Bearer <token>` (see backend routers/mobile_auth.py).
/// Bearer requests need no CSRF token and no cookies.
///
/// The backend is hosted on Render's free tier, which sleeps when idle, so the first request after
/// a pause can take up to a minute. Timeouts are generous, GETs are retried once, and [slow] turns
/// true after a few seconds so the UI can say "waking up the server".
library;

import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:http_parser/http_parser.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';

import '../config.dart';

class ApiError implements Exception {
  ApiError(this.status, this.message);
  final int? status;
  final String message;
  @override
  String toString() => message;
}

/// A file to upload (path on disk + the name/mime to send).
class UploadFile {
  UploadFile(this.path, {String? filename})
      : filename = filename ?? path.split(Platform.pathSeparator).last;
  final String path;
  final String filename;

  MediaType get mediaType {
    final n = filename.toLowerCase();
    if (n.endsWith('.png')) return MediaType('image', 'png');
    if (n.endsWith('.webp')) return MediaType('image', 'webp');
    return MediaType('image', 'jpeg');
  }

  Future<MultipartFile> toPart() =>
      MultipartFile.fromFile(path, filename: filename, contentType: mediaType);
}

class ApiClient {
  ApiClient._() {
    _dio = Dio(BaseOptions(
      baseUrl: AppConfig.apiBase,
      connectTimeout: const Duration(seconds: 60),
      sendTimeout: const Duration(seconds: 120),
      receiveTimeout: const Duration(seconds: 120),
      validateStatus: (_) => true, // we map status codes ourselves
    ));
  }
  static final ApiClient instance = ApiClient._();

  late final Dio _dio;
  String? token;

  /// Called when the server says the sign-in is no longer valid.
  VoidCallback? onUnauthorized;

  /// True while a request has been running for more than a few seconds.
  final ValueNotifier<bool> slow = ValueNotifier(false);
  int _pending = 0;
  int _generation = 0;

  Options get _opts => Options(
        headers: {if (token != null) 'Authorization': 'Bearer $token'},
      );

  Future<T> _track<T>(Future<T> Function() run) async {
    _pending++;
    final gen = ++_generation;
    Future.delayed(const Duration(seconds: 6), () {
      if (_pending > 0 && gen == _generation) slow.value = true;
    });
    try {
      return await run();
    } finally {
      _pending--;
      if (_pending <= 0) {
        _pending = 0;
        slow.value = false;
      }
    }
  }

  Map<String, dynamic> _map(Object? data) =>
      data is Map ? Map<String, dynamic>.from(data) : <String, dynamic>{};

  ApiError _error(Response<dynamic> r) {
    final m = _map(r.data);
    final raw = m['error'] ?? m['detail'];
    final text = raw is String && raw.isNotEmpty
        ? raw
        : (r.statusCode == 413
            ? 'The upload is too large.'
            : 'Something went wrong. Please try again.');
    return ApiError(r.statusCode, text);
  }

  ApiError _network(DioException e) {
    switch (e.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
        return ApiError(null, 'The server is taking too long to answer. Please try again in a moment.');
      default:
        return ApiError(null, 'Could not reach the server. Check your internet connection.');
    }
  }

  Future<Map<String, dynamic>> _send(
    String method,
    String path, {
    Object? data,
    bool retry = false,
  }) {
    return _track(() async {
      for (var attempt = 0;; attempt++) {
        try {
          final r = await _dio.request<dynamic>(path,
              data: data, options: _opts.copyWith(method: method));
          final code = r.statusCode ?? 0;
          if (code >= 200 && code < 300) return _map(r.data);
          if (code == 401) onUnauthorized?.call();
          throw _error(r);
        } on DioException catch (e) {
          if (retry && attempt == 0) continue; // Render may still be waking up
          throw _network(e);
        }
      }
    });
  }

  Future<Map<String, dynamic>> get(String path) => _send('GET', path, retry: true);

  Future<Map<String, dynamic>> post(String path, {Map<String, dynamic>? json}) =>
      _send('POST', path, data: json ?? <String, dynamic>{});

  Future<Map<String, dynamic>> postForm(String path, FormData form) =>
      _send('POST', path, data: form);

  Future<Map<String, dynamic>> delete(String path) => _send('DELETE', path);

  /// Builds a multipart body. Values are sent as strings; [files] maps a field name to its file.
  Future<FormData> buildForm(Map<String, String> fields, {Map<String, UploadFile?> files = const {}}) async {
    final form = FormData();
    fields.forEach((k, v) => form.fields.add(MapEntry(k, v)));
    for (final e in files.entries) {
      final f = e.value;
      if (f != null) form.files.add(MapEntry(e.key, await f.toPart()));
    }
    return form;
  }

  /// Authenticated download (private images and PDFs need the bearer token).
  Future<Uint8List> bytes(String path) {
    return _track(() async {
      try {
        final r = await _dio.get<List<int>>(path,
            options: _opts.copyWith(responseType: ResponseType.bytes));
        final code = r.statusCode ?? 0;
        if (code == 401) onUnauthorized?.call();
        if (code < 200 || code >= 300) {
          throw ApiError(code, 'That file could not be opened.');
        }
        return Uint8List.fromList(r.data ?? const <int>[]);
      } on DioException catch (e) {
        throw _network(e);
      }
    });
  }

  /// Downloads a PDF and opens it with the phone's PDF viewer.
  Future<void> openPdf(String path, String name) async {
    final data = await bytes(path);
    final dir = await getTemporaryDirectory();
    final file = File('${dir.path}/$name.pdf');
    await file.writeAsBytes(data, flush: true);
    final result = await OpenFilex.open(file.path, type: 'application/pdf');
    if (result.type != ResultType.done) {
      throw ApiError(null, 'No PDF viewer was found on this phone.');
    }
  }
}

final api = ApiClient.instance;
