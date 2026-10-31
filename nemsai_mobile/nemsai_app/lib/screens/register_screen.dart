/// register_screen.dart - personal-Gmail registration (port of the website's Register.jsx),
/// with the ID / COR scanner instead of file inputs.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/api_client.dart';
import '../api/auth_state.dart';
import '../theme.dart';
import '../util/image_tools.dart';
import '../widgets/common.dart';
import '../widgets/id_scanner_slot.dart';
import '../widgets/registration_help.dart';
import 'document_scan_screen.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({super.key});
  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  String _type = 'student';
  late final TextEditingController _fullName;
  final _idNumber = TextEditingController();
  final _department = TextEditingController();
  String _docType = 'school_id'; // school_id | cor
  File? _idFront, _idBack, _cor;
  bool _consent = false;
  bool _extracting = false;
  String _extractionMessage = '';
  int _extractionRequest = 0;
  bool _busy = false;
  String _error = '';
  bool _submitted = false;
  String _resultMessage = '';

  @override
  void initState() {
    super.initState();
    _fullName = TextEditingController(text: context.read<AuthState>().pending?.googleName ?? '');
  }

  @override
  void dispose() {
    _fullName.dispose();
    _idNumber.dispose();
    _department.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_extracting) return setState(() => _error = 'Wait for document reading to finish, or enter the values manually.');
    final auth = context.read<AuthState>();
    setState(() => _error = '');
    final name = _fullName.text.trim();
    final idNo = _idNumber.text.trim();
    if (name.length < 3) return setState(() => _error = 'Enter your full name.');

    final fields = <String, String>{'full_name': name};
    final files = <String, UploadFile?>{};
    final String endpoint;

    if (_type == 'instructor') {
      if (idNo.length < 3) return setState(() => _error = 'Enter your instructor ID number.');
      if (_department.text.trim().length < 2) return setState(() => _error = 'Enter your department.');
      fields['instructor_id'] = idNo;
      fields['department'] = _department.text.trim();
      endpoint = '/api/auth/mobile/register/instructor';
    } else {
      if (idNo.length < 3) return setState(() => _error = 'Enter a valid NEMSU school ID number.');
      if (_docType == 'school_id' && _idFront == null) {
        return setState(() => _error = 'Scan or choose a photo of your school ID.');
      }
      if (_docType == 'cor' && _cor == null) {
        return setState(() => _error = 'Scan or choose a photo of your Certificate of Registration.');
      }
      fields['student_id'] = idNo;
      fields['ai_review_consent'] = _consent ? 'true' : 'false';
      if (_docType == 'school_id') {
        files['school_id_document'] = toUpload(_idFront!, 'school-id-front');
        if (_idBack != null) files['school_id_back_document'] = toUpload(_idBack!, 'school-id-back');
      } else {
        files['cor_document'] = toUpload(_cor!, 'cor');
      }
      endpoint = '/api/auth/mobile/register/student';
    }

    setState(() => _busy = true);
    try {
      final idToken = await auth.freshIdToken();
      if (idToken == null) {
        setState(() => _error = 'Your Google sign-in expired. Go back and sign in again.');
        return;
      }
      fields['id_token'] = idToken;
      final form = await api.buildForm(fields, files: files);
      final r = await api.postForm(endpoint, form);
      setState(() {
        _resultMessage = (r['message'] ?? 'Registration submitted.') as String;
        _submitted = true;
      });
    } on ApiError catch (e) {
      setState(() => _error = e.status == 401
          ? 'Your Google sign-in expired. Go back and sign in again.'
          : e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _extractStudentInfo(File? file) async {
    if (file == null || !_consent || _type != 'student') return;
    final request = ++_extractionRequest;
    setState(() {
      _extracting = true;
      _extractionMessage = 'Reading the name and student ID from your document…';
    });
    try {
      final idToken = await context.read<AuthState>().freshIdToken();
      if (idToken == null) throw ApiError(401, 'Your Google sign-in expired. Go back and sign in again.');
      final form = await api.buildForm(
        {'id_token': idToken, 'consent': 'true'},
        files: {'scan_document': toUpload(file, 'student-document')},
      );
      final result = await api.postForm('/api/auth/mobile/register/extract-student-info', form);
      if (!mounted || request != _extractionRequest) return;
      final name = (result['full_name'] ?? '').toString();
      final id = (result['student_id'] ?? '').toString();
      if (name.isNotEmpty) _fullName.text = name;
      if (id.isNotEmpty) _idNumber.text = id;
      setState(() => _extractionMessage = (result['message'] ?? 'Check the detected values before submitting.') as String);
    } on ApiError catch (e) {
      if (mounted && request == _extractionRequest) {
        setState(() => _extractionMessage = e.message);
      }
    } catch (_) {
      if (mounted && request == _extractionRequest) {
        setState(() => _extractionMessage = 'Could not read this document. Enter the values manually.');
      }
    } finally {
      if (mounted && request == _extractionRequest) setState(() => _extracting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    final email = auth.pending?.email ?? '';

    return Scaffold(
      appBar: AppBar(
        title: const Text('Personal Gmail registration'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: _busy ? null : auth.cancelRegistration,
        ),
      ),
      body: Column(children: [
        const SlowServerBanner(),
        Expanded(
          child: ListView(padding: const EdgeInsets.all(16), children: [
            Panel(
              padding: const EdgeInsets.all(18),
              child: _submitted ? _success(email, auth) : _form(email, auth),
            ),
            const SizedBox(height: 10),
            const RegistrationHelp(),
          ]),
        ),
      ]),
    );
  }

  Widget _success(String email, AuthState auth) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Application submitted',
            style: TextStyle(fontFamily: serif, fontSize: 21, fontWeight: FontWeight.w700, color: C.blueDeep)),
        const SizedBox(height: 8),
        Text(_resultMessage),
        const SizedBox(height: 8),
        Text('Sign in with $email to continue or check your account status.', style: const TextStyle(color: C.muted)),
        const SizedBox(height: 14),
        SizedBox(width: double.infinity, child: FilledButton(onPressed: auth.cancelRegistration, child: const Text('Back to sign in'))),
      ]);

  Widget _form(String email, AuthState auth) {
    final student = _type == 'student';
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Center(child: AppLogo(size: 64)),
      const SizedBox(height: 10),
      const Center(
        child: Text('NEMSU Tandag Main Campus', style: TextStyle(color: C.muted)),
      ),
      const SizedBox(height: 12),
      if (email.isNotEmpty) Text.rich(TextSpan(text: 'Personal Gmail: ', children: [TextSpan(text: email, style: const TextStyle(fontWeight: FontWeight.w700))])),
      const SizedBox(height: 12),
      if (_error.isNotEmpty) Message(_error, isError: true),
      DropdownButtonFormField<String>(
        value: _type,
        decoration: const InputDecoration(labelText: 'Register as'),
        items: const [
          DropdownMenuItem(value: 'student', child: Text('Student')),
          DropdownMenuItem(value: 'instructor', child: Text('Instructor')),
        ],
          onChanged: _busy ? null : (v) => setState(() {
            _type = v ?? 'student';
            _idNumber.clear();
            _extractionRequest++;
            _extracting = false;
            _extractionMessage = '';
          }),
      ),
      const SizedBox(height: 12),
      if (!student) ...[
        TextField(
          controller: _fullName,
          maxLength: 120,
          textCapitalization: TextCapitalization.words,
          decoration: const InputDecoration(labelText: 'Full name', counterText: ''),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _idNumber,
          maxLength: 50,
          decoration: const InputDecoration(labelText: 'Instructor ID number', counterText: ''),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _department,
          maxLength: 120,
          decoration: const InputDecoration(labelText: 'Department', counterText: ''),
        ),
        const SizedBox(height: 10),
        const Text('Your instructor account will remain pending until an administrator reviews your details.',
            style: TextStyle(color: C.muted, fontSize: 13)),
      ] else ...[
        DropdownButtonFormField<String>(
          value: _docType,
          decoration: const InputDecoration(labelText: 'Document to scan'),
          items: const [
            DropdownMenuItem(value: 'school_id', child: Text('NEMSU School ID')),
            DropdownMenuItem(value: 'cor', child: Text('Certificate of Registration (COR)')),
          ],
          onChanged: _busy
              ? null
              : (v) => setState(() {
                    _docType = v ?? 'school_id';
                    _idFront = null;
                    _idBack = null;
                    _cor = null;
                    _fullName.clear();
                    _idNumber.clear();
                    _extractionRequest++;
                    _extracting = false;
                    _extractionMessage = '';
                  }),
        ),
        const SizedBox(height: 10),
        const Text(
          'To autofill your name and student ID, choose a document and agree to AI reading below. The fields remain editable if the result needs correction.',
          style: TextStyle(color: C.muted, fontSize: 13, height: 1.4),
        ),
        const SizedBox(height: 8),
        const Text(
          'Choose either your school ID or your COR, then scan it with the camera or upload an image. '
          'School ID automatic screening requires front and back; a COR can be screened by itself.',
          style: TextStyle(color: C.muted, fontSize: 13, height: 1.4),
        ),
        const SizedBox(height: 12),
        if (_docType == 'school_id') ...[
          IdScannerSlot(
            kind: ScanKind.idFront,
            file: _idFront,
            required: true,
            disabled: _busy,
            onChanged: (f) {
              setState(() {
                _idFront = f;
                if (f != null) {
                  _fullName.clear();
                  _idNumber.clear();
                  _extractionMessage = '';
                }
              });
              _extractStudentInfo(f);
            },
          ),
          const SizedBox(height: 12),
          IdScannerSlot(
            kind: ScanKind.idBack,
            file: _idBack,
            disabled: _busy,
            onChanged: (f) => setState(() => _idBack = f),
          ),
          if (_idBack == null)
            const Padding(
              padding: EdgeInsets.only(top: 6),
              child: Text('Without the back, the application stays pending for admin review.',
                  style: TextStyle(color: C.muted, fontSize: 12.5)),
            ),
        ] else
          IdScannerSlot(
            kind: ScanKind.cor,
            file: _cor,
            required: true,
            disabled: _busy,
            onChanged: (f) {
              setState(() {
                _cor = f;
                if (f != null) {
                  _fullName.clear();
                  _idNumber.clear();
                  _extractionMessage = '';
                }
              });
              _extractStudentInfo(f);
            },
          ),
        const SizedBox(height: 12),
        CheckboxListTile(
          contentPadding: EdgeInsets.zero,
          controlAffinity: ListTileControlAffinity.leading,
          value: _consent,
          onChanged: _busy ? null : (v) {
            final consent = v ?? false;
            setState(() {
              _consent = consent;
              if (!consent) {
                _extractionRequest++;
                _extracting = false;
                _extractionMessage = 'AI autofill is off. You can enter your name and student ID manually.';
              }
            });
            if (consent) _extractStudentInfo(_docType == 'school_id' ? _idFront : _cor);
          },
          title: const Text(
            'I agree to send my ID/COR scan to the configured AI provider to extract only my printed full name and '
            'student ID for form autofill, and to visually screen the document. I will check and correct the detected '
            'values before submitting. The provider may process these fields; other personal fields, faces, and QR '
            'codes are not requested. Visual screening does not prove authenticity or verify signatures. Image metadata '
            'is removed first, and administrators can view the submitted scans.',
            style: TextStyle(fontSize: 12.5, height: 1.4, color: C.muted),
          ),
        ),
        if (_extracting || _extractionMessage.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(_extracting ? 'Reading your document…' : _extractionMessage,
                style: const TextStyle(color: C.muted, fontSize: 12.5)),
          ),
        const SizedBox(height: 14),
        const Text('Scan result', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16, color: C.blueDeep)),
        const SizedBox(height: 4),
        const Text('Check the detected values and correct them if needed.',
            style: TextStyle(color: C.muted, fontSize: 12.5)),
        const SizedBox(height: 10),
        TextField(
          controller: _fullName,
          maxLength: 120,
          textCapitalization: TextCapitalization.words,
          decoration: const InputDecoration(labelText: 'Full name', counterText: ''),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _idNumber,
          maxLength: 50,
          decoration: const InputDecoration(labelText: 'Student ID number', counterText: ''),
        ),
      ],
      const SizedBox(height: 14),
      SizedBox(
        width: double.infinity,
        child: FilledButton(
          onPressed: _busy || _extracting ? null : _submit,
          child: Text(_busy ? 'Submitting...' : _extracting ? 'Reading document...' : 'Submit registration'),
        ),
      ),
      const SizedBox(height: 6),
      Center(
        child: TextButton(onPressed: _busy ? null : auth.cancelRegistration, child: const Text('Return to sign in')),
      ),
    ]);
  }
}
