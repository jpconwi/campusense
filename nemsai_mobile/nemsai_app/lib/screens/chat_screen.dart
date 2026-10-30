/// chat_screen.dart - the NEMSAI chat window (port of Chat.jsx): questions, suggestions, in-chat forms,
/// photo reports, map links and saved chat history.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/api_client.dart';
import '../api/auth_state.dart';
import '../config.dart';
import '../theme.dart';
import '../util/image_tools.dart';
import '../widgets/common.dart';
import '../widgets/markdown_text.dart';
import '../widgets/photo_report_card.dart';
import '../widgets/record_form.dart';
import '../widgets/skeleton.dart';

const _formTypes = {
  'concern_form': 'concern',
  'report_form': 'report',
  'feedback_form': 'feedback',
  'reservation_form': 'reservation',
  'faculty_form': 'faculty',
};

const _quick = [
  'What equipment can I borrow?',
  'How do I report a broken facility?',
  'Where is the NEMSU Tandag campus?',
  'Where is the library?',
  'Which canteen is near the CBM area?',
];
const _reserveQuick = 'How do I reserve a room or facility?'; // instructors only

enum _Kind { typing, text, form, photo, map, note, success }

class _Item {
  _Item(this.id, this.role, this.kind,
      {this.text = '', this.time = '', this.error = false, this.suggestions = const [], this.image, this.formKind, this.prefill, this.result, this.map});
  final int id;
  final String role; // user | ai
  final _Kind kind;
  final String text;
  final String time;
  final bool error;
  final List<String> suggestions;
  final File? image;
  final String? formKind;
  final Map<String, dynamic>? prefill;
  final Map<String, dynamic>? result;
  final Map<String, dynamic>? map;
}

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});
  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final List<_Item> _items = [];
  final _text = TextEditingController();
  final _scroll = ScrollController();
  int _nextId = 1;
  int? _sessionId;
  bool _busy = false;
  bool _loadingChat = false;
  File? _photo;
  String _photoError = '';

  @override
  void dispose() {
    _text.dispose();
    _scroll.dispose();
    super.dispose();
  }

  _Item _add(String role, _Kind kind, {String text = '', bool error = false, List<String> suggestions = const [], File? image, String? formKind, Map<String, dynamic>? prefill, Map<String, dynamic>? result, Map<String, dynamic>? map}) {
    final item = _Item(_nextId++, role, kind,
        text: text, time: clock(DateTime.now()), error: error, suggestions: suggestions, image: image, formKind: formKind, prefill: prefill, result: result, map: map);
    setState(() => _items.add(item));
    _toBottom();
    return item;
  }

  void _remove(_Item item) => setState(() => _items.remove(item));

  void _toBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(_scroll.position.maxScrollExtent, duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
      }
    });
  }

  void _newChat() {
    setState(() {
      _items.clear();
      _sessionId = null;
      _nextId = 1;
      _text.clear();
      _photo = null;
      _photoError = '';
    });
  }

  // ------------------------------------------------------------------ sending
  Future<void> _send([String? preset]) async {
    if (_photo != null && preset == null) return _sendPhoto();
    final question = (preset ?? _text.text).trim();
    if (question.isEmpty || _busy) return;
    _add('user', _Kind.text, text: question);
    _text.clear();
    setState(() => _busy = true);
    final typing = _add('ai', _Kind.typing);
    try {
      final data = await api.post('/api/ask', json: {'question': question, 'session_id': _sessionId});
      _remove(typing);
      if (data['session_id'] is num) _sessionId = (data['session_id'] as num).toInt();
      _add('ai', _Kind.text,
          text: '${data['answer'] ?? ''}',
          suggestions: ((data['suggestions'] as List?) ?? const []).map((e) => '$e').toList());
      if (data['type'] == 'map' && data['map'] is Map) {
        _add('ai', _Kind.map, map: Map<String, dynamic>.from(data['map'] as Map));
      }
      final formKind = _formTypes['${data['type']}'];
      if (formKind != null) {
        _add('ai', _Kind.form,
            formKind: formKind, prefill: data['prefill'] is Map ? Map<String, dynamic>.from(data['prefill'] as Map) : null);
      }
    } on ApiError catch (e) {
      _remove(typing);
      if (e.status != 401) _add('ai', _Kind.text, error: true, text: 'Could not get an answer. ${e.message} Please try again.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _sendPhoto() async {
    final file = _photo;
    if (_busy || file == null) return;
    final description = _text.text.trim();
    _add('user', _Kind.text, text: description.isEmpty ? '(photo only)' : description, image: file);
    setState(() {
      _photo = null;
      _busy = true;
    });
    _text.clear();
    final typing = _add('ai', _Kind.typing);
    try {
      final fields = <String, String>{
        if (description.isNotEmpty) 'description': description,
        if (_sessionId != null) 'session_id': '$_sessionId',
      };
      final form = await api.buildForm(fields, files: {'image': toUpload(file, 'photo')});
      final data = await api.postForm('/api/reports/photo/analyze', form);
      _remove(typing);
      if (data['session_id'] is num) _sessionId = (data['session_id'] as num).toInt();
      _add('ai', _Kind.text, text: '${data['message'] ?? ''}');
      _add('ai', _Kind.photo, result: data, image: file);
    } on ApiError catch (e) {
      _remove(typing);
      if (e.status != 401) _add('ai', _Kind.text, error: true, text: "I couldn't check that photo. ${e.message}");
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _pickPhoto(ImageSource source) async {
    try {
      final x = await ImagePicker().pickImage(source: source, maxWidth: 2400, maxHeight: 2400, imageQuality: 85);
      if (x == null) return;
      var path = x.path;
      if (sniffImage(path) == null) {
        setState(() => _photoError = 'Please choose a PNG, JPG or WEBP photo.');
        return;
      }
      if (File(path).lengthSync() > AppConfig.maxImageBytes) path = await shrinkToJpeg(path, '${path}_small.jpg');
      if (File(path).lengthSync() > AppConfig.maxImageBytes) {
        setState(() => _photoError = 'The photo must be 5 MB or smaller.');
        return;
      }
      setState(() {
        _photo = File(path);
        _photoError = '';
      });
    } catch (_) {
      setState(() => _photoError = 'The photo could not be opened.');
    }
  }

  void _photoMenu() {
    showModalBottomSheet<void>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          ListTile(
            leading: const Icon(Icons.photo_camera_outlined),
            title: const Text('Take a photo'),
            onTap: () {
              Navigator.pop(ctx);
              _pickPhoto(ImageSource.camera);
            },
          ),
          ListTile(
            leading: const Icon(Icons.image_outlined),
            title: const Text('Upload a photo'),
            onTap: () {
              Navigator.pop(ctx);
              _pickPhoto(ImageSource.gallery);
            },
          ),
        ]),
      ),
    );
  }

  // ------------------------------------------------------------------ history
  void _restore(List<dynamic> messages) {
    final rows = <_Item>[];
    var id = 1;
    String timeOf(Object? s) {
      final d = DateTime.tryParse('$s');
      return d == null ? '' : clock(d.toLocal());
    }

    for (final raw in messages) {
      final m = Map<String, dynamic>.from(raw as Map);
      final time = timeOf(m['created_at']);
      if (m['role'] == 'user') {
        rows.add(_Item(id++, 'user', _Kind.text, text: '${m['text'] ?? ''}', time: time));
        continue;
      }
      rows.add(_Item(id++, 'ai', _Kind.text,
          text: '${m['text'] ?? ''}',
          time: time,
          suggestions: ((m['suggestions'] as List?) ?? const []).map((e) => '$e').toList()));
      if (m['type'] == 'map' && m['map'] is Map) {
        rows.add(_Item(id++, 'ai', _Kind.map, map: Map<String, dynamic>.from(m['map'] as Map)));
      }
      if (_formTypes.containsKey('${m['type']}')) {
        rows.add(_Item(id++, 'ai', _Kind.note, text: 'A form was shown here. Ask again to open a new one.'));
      }
    }
    setState(() {
      _items
        ..clear()
        ..addAll(rows);
      _nextId = id;
    });
    _toBottom();
  }

  Future<void> _openChat(int id) async {
    setState(() {
      _items.clear();
      _loadingChat = true;
      _sessionId = null;
    });
    try {
      final d = await api.get('/api/chats/$id');
      _sessionId = (d['id'] as num).toInt();
      _restore((d['messages'] as List?) ?? const []);
    } on ApiError {
      // deleted meanwhile
    } finally {
      if (mounted) setState(() => _loadingChat = false);
    }
  }

  void _history() {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (ctx) => _HistorySheet(
        activeId: _sessionId,
        onOpen: (id) {
          Navigator.pop(ctx);
          _openChat(id);
        },
        onDeleted: (id) {
          if (id == null || id == _sessionId) _newChat();
        },
      ),
    );
  }

  // ---------------------------------------------------------------------- UI
  @override
  Widget build(BuildContext context) {
    final user = context.watch<AuthState>().user!;
    final extra = ['Show my pending concerns'];
    final cards = <List<String>>[
      if (user.isInstructor) ['Reserve a facility', _reserveQuick],
      ['Report a concern', 'How do I report a broken facility?'],
      ['Find a campus location', 'Where is the NEMSU Tandag campus?'],
      ['Borrow equipment', 'What equipment can I borrow?'],
    ];

    return AppScaffold(
      title: 'Campus AI',
      current: '/ai',
      actions: [
        IconButton(onPressed: _history, icon: const Icon(Icons.history), tooltip: 'Recent chats'),
        IconButton(onPressed: _busy ? null : _newChat, icon: const Icon(Icons.add_comment_outlined), tooltip: 'New chat'),
      ],
      body: Column(children: [
        Expanded(
          child: _loadingChat
              ? const ChatSkeleton()
              : _items.isEmpty
                  ? _welcome(user, cards)
                  : ListView.builder(
                      controller: _scroll,
                      padding: const EdgeInsets.fromLTRB(12, 14, 12, 8),
                      itemCount: _items.length,
                      itemBuilder: (_, i) => _row(_items[i]),
                    ),
        ),
        _composer(extra),
      ]),
    );
  }

  Widget _welcome(AppUser user, List<List<String>> cards) => ListView(
        padding: const EdgeInsets.all(20),
        children: [
          const SizedBox(height: 8),
          const Center(child: AppLogo(size: 72)),
          const SizedBox(height: 12),
          const Center(
            child: Text('How can I help you today?',
                style: TextStyle(fontFamily: serif, fontSize: 23, fontWeight: FontWeight.w700, color: C.blueDeep)),
          ),
          const SizedBox(height: 4),
          const Center(child: Text('Your NEMSU Tandag Main Campus Assistant', style: TextStyle(color: C.muted))),
          const SizedBox(height: 18),
          for (final c in cards) ...[
            Material(
              color: Colors.white,
              borderRadius: BorderRadius.circular(12),
              child: InkWell(
                borderRadius: BorderRadius.circular(12),
                onTap: () => _send(c[1]),
                child: Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(borderRadius: BorderRadius.circular(12), border: Border.all(color: C.line)),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(c[0], style: const TextStyle(fontWeight: FontWeight.w700, color: C.blueDeep)),
                    const SizedBox(height: 2),
                    Text(c[1], style: const TextStyle(color: C.muted, fontSize: 13.5)),
                  ]),
                ),
              ),
            ),
            const SizedBox(height: 10),
          ],
          const SizedBox(height: 6),
          const Text("Something broken or unsafe? Tap the camera button to take or upload a photo, and say what's wrong.",
              style: TextStyle(color: C.muted, fontSize: 13)),
          const SizedBox(height: 6),
          if (user.isInstructor)
            const Text('Instructors who cannot come to school can type "I am sick and cannot come to school" to file an availability report.',
                style: TextStyle(color: C.muted, fontSize: 13))
          else
            const Text('You can ask "Is Sir JP available today?" to check whether an instructor is in school.',
                style: TextStyle(color: C.muted, fontSize: 13)),
        ],
      );

  Widget _row(_Item item) {
    final ai = item.role == 'ai';
    final maxW = MediaQuery.of(context).size.width * (item.kind == _Kind.form || item.kind == _Kind.photo ? 0.96 : 0.84);

    Widget bubble(Widget child, {bool user = false, bool err = false}) => Container(
          constraints: BoxConstraints(maxWidth: maxW),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
          decoration: BoxDecoration(
            color: err ? const Color(0xFFFBE0E2) : (user ? C.blue : Colors.white),
            borderRadius: BorderRadius.only(
              topLeft: const Radius.circular(16),
              topRight: const Radius.circular(16),
              bottomLeft: Radius.circular(user ? 16 : 4),
              bottomRight: Radius.circular(user ? 4 : 16),
            ),
            border: user ? null : Border.all(color: err ? C.error : C.line),
          ),
          child: child,
        );

    Widget content;
    switch (item.kind) {
      case _Kind.typing:
        content = bubble(const ReplySkeleton());
      case _Kind.text:
        content = Column(crossAxisAlignment: ai ? CrossAxisAlignment.start : CrossAxisAlignment.end, children: [
          bubble(
            Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              if (item.image != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(8),
                    child: Image.file(item.image!, width: 200, fit: BoxFit.cover),
                  ),
                ),
              if (ai && !item.error)
                MarkdownText(item.text)
              else
                Text(item.text, style: TextStyle(color: item.error ? C.error : Colors.white, fontSize: 15, height: 1.4)),
            ]),
            user: !ai,
            err: item.error,
          ),
          if (item.suggestions.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Wrap(spacing: 8, runSpacing: 6, children: [
                for (final q in item.suggestions)
                  ActionChip(label: Text(q, style: const TextStyle(fontSize: 13)), onPressed: _busy ? null : () => _send(q)),
              ]),
            ),
          Padding(
            padding: const EdgeInsets.only(top: 3),
            child: Text(item.time, style: const TextStyle(color: C.muted, fontSize: 11)),
          ),
        ]);
      case _Kind.form:
        content = bubble(RecordForm(
          kind: item.formKind!,
          prefill: item.prefill,
          onSuccess: (r) => _add('ai', _Kind.success, result: r),
        ));
      case _Kind.photo:
        content = SizedBox(
          width: maxW,
          child: PhotoReportCard(
            result: item.result!,
            preview: item.image,
            onMessage: (t) => _add('ai', _Kind.text, text: t),
            onSent: (r) => _add('ai', _Kind.success, result: r),
            onDiscarded: () => _add('ai', _Kind.text, text: 'No problem, I removed the photo. Nothing was sent.'),
          ),
        );
      case _Kind.map:
        content = _mapCard(item.map!, maxW);
      case _Kind.note:
        content = bubble(Text(item.text, style: const TextStyle(fontStyle: FontStyle.italic, color: C.muted)));
      case _Kind.success:
        content = SizedBox(width: maxW, child: SuccessCard(result: item.result!));
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        mainAxisAlignment: ai ? MainAxisAlignment.start : MainAxisAlignment.end,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (ai) ...[
            const Padding(padding: EdgeInsets.only(top: 2, right: 8), child: AppLogo(size: 30)),
          ],
          Flexible(child: content),
        ],
      ),
    );
  }

  /// The website shows an embedded Google map; on the phone we open the Maps app instead.
  Widget _mapCard(Map<String, dynamic> map, double maxW) {
    final url = '${map['url'] ?? ''}';
    return Container(
      width: maxW,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(14), border: Border.all(color: C.line)),
      child: Row(children: [
        const CircleAvatar(backgroundColor: C.blueSoft, child: Icon(Icons.place_outlined, color: C.blue)),
        const SizedBox(width: 12),
        Expanded(child: Text('${map['title'] ?? 'Map'}', style: const TextStyle(fontWeight: FontWeight.w700))),
        TextButton(
          onPressed: url.isEmpty ? null : () => launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication),
          child: const Text('Open in Maps'),
        ),
      ]),
    );
  }

  Widget _composer(List<String> extra) {
    return Container(
      decoration: const BoxDecoration(color: Colors.white, border: Border(top: BorderSide(color: C.line))),
      padding: EdgeInsets.fromLTRB(10, 8, 10, 8 + MediaQuery.of(context).padding.bottom * 0),
      child: SafeArea(
        top: false,
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          SizedBox(
            height: 38,
            child: ListView(scrollDirection: Axis.horizontal, children: [
              for (final q in [..._quick, ...extra])
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: ActionChip(
                    label: Text(q, style: const TextStyle(fontSize: 12.5)),
                    onPressed: _busy ? null : () => _send(q),
                  ),
                ),
            ]),
          ),
          if (_photo != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Row(children: [
                ClipRRect(borderRadius: BorderRadius.circular(8), child: Image.file(_photo!, width: 48, height: 48, fit: BoxFit.cover)),
                const SizedBox(width: 10),
                const Expanded(
                  child: Text('Photo ready. Add a description (optional), then press send.',
                      style: TextStyle(fontSize: 12.5, color: C.muted)),
                ),
                TextButton(onPressed: () => setState(() => _photo = null), child: const Text('Remove')),
              ]),
            ),
          if (_photoError.isNotEmpty)
            Padding(padding: const EdgeInsets.only(top: 6), child: Text(_photoError, style: const TextStyle(color: C.error, fontSize: 13))),
          const SizedBox(height: 8),
          Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
            IconButton.filledTonal(
              onPressed: _busy ? null : _photoMenu,
              icon: const Icon(Icons.photo_camera_outlined),
              tooltip: 'Report a problem with a photo',
            ),
            const SizedBox(width: 8),
            Expanded(
              child: TextField(
                controller: _text,
                minLines: 1,
                maxLines: 5,
                textInputAction: TextInputAction.newline,
                decoration: InputDecoration(hintText: _photo != null ? 'Describe the problem (optional)' : 'Message NEMSAI'),
                onChanged: (_) => setState(() {}),
              ),
            ),
            const SizedBox(width: 8),
            IconButton.filled(
              style: IconButton.styleFrom(backgroundColor: C.blue, foregroundColor: Colors.white),
              onPressed: _busy || (_text.text.trim().isEmpty && _photo == null) ? null : () => _send(),
              icon: _busy
                  ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : const Icon(Icons.arrow_upward),
              tooltip: 'Send',
            ),
          ]),
        ]),
      ),
    );
  }
}

// ---------------------------------------------------------------- chat history
class _HistorySheet extends StatefulWidget {
  const _HistorySheet({required this.activeId, required this.onOpen, required this.onDeleted});
  final int? activeId;
  final void Function(int id) onOpen;
  final void Function(int? id) onDeleted;

  @override
  State<_HistorySheet> createState() => _HistorySheetState();
}

class _HistorySheetState extends State<_HistorySheet> {
  List<Map<String, dynamic>>? _chats;
  bool _failed = false;
  int _keepDays = 3;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final d = await api.get('/api/chats');
      if (!mounted) return;
      setState(() {
        _chats = ((d['chats'] as List?) ?? const []).map((e) => Map<String, dynamic>.from(e as Map)).toList();
        _keepDays = (d['keep_days'] as num?)?.toInt() ?? 3;
      });
    } on ApiError {
      if (mounted) setState(() => _failed = true);
    }
  }

  Future<void> _delete(int id) async {
    try {
      await api.delete('/api/chats/$id');
    } on ApiError {/* already gone */}
    if (!mounted) return;
    setState(() => _chats?.removeWhere((c) => c['id'] == id));
    widget.onDeleted(id);
  }

  Future<void> _clearAll() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete all chats?'),
        content: const Text('All of your saved chats will be deleted.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Delete all')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await api.delete('/api/chats');
    } on ApiError {/* ignore */}
    if (!mounted) return;
    setState(() => _chats = []);
    widget.onDeleted(null);
  }

  String _when(Object? iso) {
    final d = DateTime.tryParse('$iso')?.toLocal();
    if (d == null) return '';
    final now = DateTime.now();
    final days = DateTime(now.year, now.month, now.day).difference(DateTime(d.year, d.month, d.day)).inDays;
    if (days == 0) return 'Today ${clock(d)}';
    if (days == 1) return 'Yesterday';
    return '${d.year}-${two(d.month)}-${two(d.day)}';
  }

  @override
  Widget build(BuildContext context) {
    final chats = _chats;
    return SizedBox(
      height: MediaQuery.of(context).size.height * 0.7,
      child: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 8, 4),
          child: Row(children: [
            const Expanded(child: Text('Recent chats', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17, color: C.blueDeep))),
            if (chats != null && chats.isNotEmpty) TextButton(onPressed: _clearAll, child: const Text('Clear all')),
          ]),
        ),
        Expanded(
          child: chats == null && !_failed
              ? const ListSkeleton(rows: 5, heading: false)
              : _failed && (chats == null || chats.isEmpty)
                  ? const EmptyState(title: 'Could not load your chats', icon: Icons.cloud_off_outlined)
                  : chats!.isEmpty
                      ? EmptyState(title: 'No saved chats yet', text: 'Ask something and it shows up here.\nChats are kept for $_keepDays days.')
                      : ListView.separated(
                          itemCount: chats.length,
                          separatorBuilder: (_, __) => const Divider(height: 1, color: C.line),
                          itemBuilder: (_, i) {
                            final c = chats[i];
                            final id = (c['id'] as num).toInt();
                            return ListTile(
                              selected: id == widget.activeId,
                              title: Text('${c['title']}', maxLines: 1, overflow: TextOverflow.ellipsis),
                              subtitle: Text(_when(c['updated_at'])),
                              trailing: IconButton(icon: const Icon(Icons.delete_outline), onPressed: () => _delete(id), tooltip: 'Delete chat'),
                              onTap: () => widget.onOpen(id),
                            );
                          },
                        ),
        ),
      ]),
    );
  }
}
