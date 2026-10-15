// Right side: status chip, messages (or the empty state) and the composer.

import 'dart:convert';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:gpt_markdown/gpt_markdown.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models.dart';
import '../state.dart';
import '../text.dart';
import 'theme.dart';

class ChatPane extends StatelessWidget {
  const ChatPane({super.key, required this.state, required this.sidebarCollapsed, required this.onExpandSidebar});

  final AppState state;
  final bool sidebarCollapsed;
  final VoidCallback onExpandSidebar;

  String? get _status {
    final h = state.health;
    if (!h.available) return 'Cannot reach the local server';
    if (h.modelError != null) return h.modelError;
    final pct = state.downloadPct;
    if (pct != null) return 'Downloading model… $pct%';
    if (!state.modelReady) return 'Preparing model…';
    return null;
  }

  String get _placeholder {
    final h = state.health;
    if (!h.available) return 'Server unavailable';
    if (h.modelError != null) return 'Model unavailable';
    if (state.downloadPct != null) return 'Downloading model (first launch only)…';
    if (!state.modelReady) return 'Preparing model…';
    return 'Message…';
  }

  @override
  Widget build(BuildContext context) {
    final h = state.health;
    final messages = state.activeMessages;
    final status = _status;
    final working = h.available && h.modelError == null && !state.modelReady;
    final composer = Composer(
      key: ValueKey('composer-${state.activeId}'),
      state: state,
      enabled: state.modelReady,
      allowUploads: h.fileUploads,
      placeholder: _placeholder,
    );

    return Container(
      color: C.ground,
      child: Column(
        children: [
          SizedBox(
            height: 48,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8),
              child: Row(
                children: [
                  if (sidebarCollapsed)
                    IconBtn(icon: Icons.view_sidebar_outlined, tooltip: 'Show sidebar', onPressed: onExpandSidebar),
                  const Spacer(),
                  if (status != null)
                    Container(
                      constraints: const BoxConstraints(maxWidth: 520),
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                      decoration: BoxDecoration(
                        border: Border.all(color: C.line),
                        borderRadius: BorderRadius.circular(99),
                      ),
                      child: Row(mainAxisSize: MainAxisSize.min, children: [
                        if (working) ...[const PulseDot(), const SizedBox(width: 8)],
                        Flexible(
                          child: Text(status,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(fontSize: 11, color: C.muted)),
                        ),
                      ]),
                    ),
                ],
              ),
            ),
          ),
          if (!h.available || h.modelError != null)
            _Centered(
              child: _Notice(
                !h.available
                    ? 'The local backend isn’t reachable. Close LocalChat and start it again.'
                    : 'Model unavailable — ${h.modelError}',
              ),
            ),
          if (messages.isEmpty)
            Expanded(
              child: Center(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 64),
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: contentMaxWidth),
                    child: Column(children: [
                      Image.asset('assets/logo-nobodywho.png', height: 28),
                      const SizedBox(height: 20),
                      const Text('What can I help with?',
                          style: TextStyle(fontSize: 28, fontWeight: FontWeight.w600, letterSpacing: -0.4)),
                      const SizedBox(height: 28),
                      composer,
                    ]),
                  ),
                ),
              ),
            )
          else ...[
            Expanded(child: MessageList(key: ValueKey(state.activeId), state: state, messages: messages)),
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
              child: _Centered(
                child: Column(children: [
                  composer,
                  const SizedBox(height: 8),
                  const Text('Responses are generated locally on your machine.',
                      style: TextStyle(fontSize: 11, color: C.muted)),
                ]),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _Centered extends StatelessWidget {
  const _Centered({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => Center(
        child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: contentMaxWidth), child: child),
      );
}

class _Notice extends StatelessWidget {
  const _Notice(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        margin: const EdgeInsets.fromLTRB(16, 0, 16, 4),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: C.bubble,
          border: Border.all(color: C.line),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Text(text, style: const TextStyle(fontSize: 12.5, color: C.muted)),
      );
}

// ---------------------------------------------------------------------------
// Message list: stays pinned to the bottom while an answer streams, unless the
// user scrolls up; then a "scroll to bottom" button appears.

class MessageList extends StatefulWidget {
  const MessageList({super.key, required this.state, required this.messages});

  final AppState state;
  final List<Message> messages;

  @override
  State<MessageList> createState() => _MessageListState();
}

class _MessageListState extends State<MessageList> {
  final _scroll = ScrollController();
  bool _pinned = true;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(() {
      if (!_scroll.hasClients) return;
      final p = _scroll.position;
      final pinned = p.maxScrollExtent - p.pixels < 56;
      if (pinned != _pinned) setState(() => _pinned = pinned);
    });
    _jumpToEnd();
  }

  @override
  void didUpdateWidget(MessageList old) {
    super.didUpdateWidget(old);
    if (_pinned) _jumpToEnd();
  }

  void _jumpToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) _scroll.jumpTo(_scroll.position.maxScrollExtent);
    });
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final msgs = widget.messages;
    return Stack(
      children: [
        SelectionArea(
          child: ListView.builder(
            controller: _scroll,
            padding: const EdgeInsets.symmetric(vertical: 24),
            itemCount: msgs.length,
            itemBuilder: (_, i) => Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
              child: _Centered(
                child: MessageView(
                  key: ValueKey(msgs[i].id),
                  state: widget.state,
                  message: msgs[i],
                  isLast: i == msgs.length - 1,
                ),
              ),
            ),
          ),
        ),
        if (!_pinned)
          Positioned(
            bottom: 12,
            left: 0,
            right: 0,
            child: Center(
              child: Material(
                color: C.ground,
                shape: const CircleBorder(side: BorderSide(color: C.line)),
                elevation: 2,
                shadowColor: const Color(0x220A0A0A),
                child: IconButton(
                  tooltip: 'Scroll to bottom',
                  icon: const Icon(Icons.keyboard_arrow_down, size: 20, color: C.ink),
                  onPressed: () {
                    _scroll.animateTo(_scroll.position.maxScrollExtent,
                        duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
                    setState(() => _pinned = true);
                  },
                ),
              ),
            ),
          ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------

class MessageView extends StatefulWidget {
  const MessageView({super.key, required this.state, required this.message, required this.isLast});

  final AppState state;
  final Message message;
  final bool isLast;

  @override
  State<MessageView> createState() => _MessageViewState();
}

class _MessageViewState extends State<MessageView> {
  bool _hover = false;
  bool _copied = false;

  @override
  Widget build(BuildContext context) {
    final m = widget.message;
    if (m.role == 'user') return _user(m);

    final streaming = m.status == 'streaming';
    final split = splitThinking(m.content);
    final showLoading = streaming && m.content.isEmpty;

    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            margin: const EdgeInsets.only(top: 4),
            width: 24,
            height: 24,
            decoration: BoxDecoration(color: C.ground, shape: BoxShape.circle, border: Border.all(color: C.line)),
            child: Center(
              child: Container(
                width: 10,
                height: 10,
                decoration: const BoxDecoration(color: C.ink, shape: BoxShape.circle),
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (split.thinking != null)
                  ThinkingBlock(text: split.thinking!, streaming: streaming && !split.thinkingDone),
                ToolCallsBlock(calls: m.toolCalls),
                if (showLoading)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 8),
                    child: Row(children: [
                      PulseDot(),
                      SizedBox(width: 4),
                      PulseDot(delay: Duration(milliseconds: 160)),
                      SizedBox(width: 4),
                      PulseDot(delay: Duration(milliseconds: 320)),
                    ]),
                  )
                else if (split.thinking == null || split.thinkingDone || split.answer.trim().isNotEmpty)
                  MarkdownText(split.answer, streaming: streaming),
                if (m.status == 'error') ...[
                  const SizedBox(height: 8),
                  _Notice(m.error?.isNotEmpty == true ? m.error! : 'Something went wrong while generating.'),
                ],
                if (!streaming) ...[
                  if (m.stats != null && m.stats!.tokensPerSecond > 0)
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Text(
                        '${m.stats!.tokensPerSecond >= 100 ? m.stats!.tokensPerSecond.round() : m.stats!.tokensPerSecond.toStringAsFixed(1)} tok/s'
                        '${m.stats!.tokens > 0 ? ' · ${m.stats!.tokens} tokens' : ''}'
                        '${m.status == 'stopped' ? ' · stopped' : ''}',
                        style: const TextStyle(fontSize: 12, color: C.muted),
                      ),
                    ),
                  if (m.content.isNotEmpty)
                    Opacity(
                      opacity: _hover ? 1 : 0,
                      child: Row(children: [
                        IconBtn(
                          icon: _copied ? Icons.check : Icons.copy_outlined,
                          tooltip: 'Copy',
                          size: 15,
                          onPressed: () async {
                            await Clipboard.setData(ClipboardData(text: split.answer.trim()));
                            setState(() => _copied = true);
                            Future.delayed(const Duration(milliseconds: 1400), () {
                              if (mounted) setState(() => _copied = false);
                            });
                          },
                        ),
                        if (widget.isLast && m.status != 'error')
                          IconBtn(
                            icon: Icons.refresh,
                            tooltip: 'Regenerate',
                            size: 16,
                            onPressed: widget.state.isStreaming ? null : widget.state.regenerate,
                          ),
                      ]),
                    ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _user(Message m) {
    return Align(
      alignment: Alignment.centerRight,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: contentMaxWidth * 0.85),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            if (m.attachments.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Wrap(
                  alignment: WrapAlignment.end,
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (var i = 0; i < m.attachments.length; i++) _attachment(m, i),
                  ],
                ),
              ),
            if (m.content.isNotEmpty)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                decoration: BoxDecoration(color: C.bubble, borderRadius: BorderRadius.circular(10)),
                child: Text(m.content, style: const TextStyle(fontSize: 15, height: 1.6)),
              ),
          ],
        ),
      ),
    );
  }

  Widget _attachment(Message m, int i) {
    final a = m.attachments[i];
    if (a.isImage) {
      final image = a.previewBytes != null
          ? Image.memory(a.previewBytes!, fit: BoxFit.cover)
          : Image.network(widget.state.api.attachmentUrl(m.id, i).toString(),
              fit: BoxFit.cover, errorBuilder: (_, _, _) => _fileChip(a.name));
      return Tooltip(
        message: a.name,
        child: ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: ConstrainedBox(constraints: const BoxConstraints(maxHeight: 176, maxWidth: 220), child: image),
        ),
      );
    }
    return _fileChip(a.name);
  }

  Widget _fileChip(String name) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(border: Border.all(color: C.line), borderRadius: BorderRadius.circular(8)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.insert_drive_file_outlined, size: 14, color: C.muted),
          const SizedBox(width: 6),
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 200),
            child: Text(name, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12)),
          ),
        ]),
      );
}

/// Assistant Markdown: headings, lists, tables, code blocks (highlighted, with
/// a copy button), links (open in the browser) and maths.
class MarkdownText extends StatelessWidget {
  const MarkdownText(this.text, {super.key, this.streaming = false, this.fontSize = 15.5});

  final String text;
  final bool streaming;
  final double fontSize;

  @override
  Widget build(BuildContext context) {
    return GptMarkdown(
      normalizeMath(text),
      isStreaming: streaming,
      style: TextStyle(fontSize: fontSize, height: 1.65, color: C.ink),
      onLinkTap: (url, _) {
        final uri = Uri.tryParse(url);
        if (uri != null) launchUrl(uri);
      },
      styleSheet: GptMarkdownStyleSheet(
        codeBlock: CodeBlockStyle(
          backgroundColor: C.bubble,
          borderColor: C.line,
          borderRadius: const Radius.circular(10),
          fontFamily: monoFont,
          fontSize: 13,
          textColor: C.ink,
        ),
        inlineCode: InlineCodeStyle(fontFamily: monoFont),
      ),
    );
  }
}

/// A reasoning model's thoughts, in a collapsible box above the answer.
class ThinkingBlock extends StatefulWidget {
  const ThinkingBlock({super.key, required this.text, required this.streaming});

  final String text;
  final bool streaming;

  @override
  State<ThinkingBlock> createState() => _ThinkingBlockState();
}

class _ThinkingBlockState extends State<ThinkingBlock> {
  bool _open = true;

  @override
  Widget build(BuildContext context) {
    return _Box(
      header: Row(children: [
        if (widget.streaming) ...[const PulseDot(), const SizedBox(width: 6)],
        Text(widget.streaming ? 'THINKING…' : 'THOUGHT PROCESS', style: _labelStyle),
      ]),
      open: _open,
      onToggle: () => setState(() => _open = !_open),
      body: MarkdownText(widget.text, streaming: widget.streaming, fontSize: 13.5),
    );
  }
}

/// The tools the model called for this answer: what it asked for and what the
/// tool returned (see backend/tools.py).
class ToolCallsBlock extends StatelessWidget {
  const ToolCallsBlock({super.key, required this.calls});

  final List<ToolCall> calls;

  @override
  Widget build(BuildContext context) {
    if (calls.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Column(children: [for (final c in calls) _ToolCallView(key: ValueKey(c.id), call: c)]),
    );
  }
}

class _ToolCallView extends StatefulWidget {
  const _ToolCallView({super.key, required this.call});

  final ToolCall call;

  @override
  State<_ToolCallView> createState() => _ToolCallViewState();
}

class _ToolCallViewState extends State<_ToolCallView> {
  bool _open = false;

  @override
  Widget build(BuildContext context) {
    final c = widget.call;
    final running = c.status == 'running';
    final args = c.args.entries.map((e) => '${e.key}: ${jsonEncode(e.value)}').join(', ');
    final mono = TextStyle(fontFamily: monoFont, fontSize: 12, color: C.ink);
    return _Box(
      highlighted: running,
      open: _open && !running,
      onToggle: running ? null : () => setState(() => _open = !_open),
      header: Row(children: [
        running
            ? const SizedBox(width: 12, height: 12, child: CircularProgressIndicator(strokeWidth: 2, color: C.ink))
            : const Icon(Icons.build_outlined, size: 13, color: C.muted),
        const SizedBox(width: 6),
        Text(running ? 'USING TOOL…' : (c.status == 'error' ? 'TOOL FAILED' : 'USED TOOL'),
            style: _labelStyle.copyWith(color: running ? C.ink : C.muted)),
        const SizedBox(width: 6),
        Flexible(
          child: Text.rich(
            TextSpan(text: c.name, style: mono, children: [
              TextSpan(text: '($args)', style: mono.copyWith(color: C.muted)),
            ]),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ]),
      body: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('THE MODEL ASKED FOR', style: _labelStyle),
        const SizedBox(height: 4),
        Text('${c.name}($args)', style: mono),
        const SizedBox(height: 8),
        const Text('THE TOOL RETURNED', style: _labelStyle),
        const SizedBox(height: 4),
        ConstrainedBox(
          constraints: const BoxConstraints(maxHeight: 256),
          child: SingleChildScrollView(child: Text(c.result ?? '', style: mono)),
        ),
      ]),
    );
  }
}

const _labelStyle = TextStyle(fontSize: 11, fontWeight: FontWeight.w500, letterSpacing: 0.5, color: C.muted);

/// Bordered, collapsible box used by the thinking and tool-call blocks.
class _Box extends StatelessWidget {
  const _Box({required this.header, required this.body, required this.open, this.onToggle, this.highlighted = false});

  final Widget header;
  final Widget body;
  final bool open;
  final VoidCallback? onToggle;
  final bool highlighted;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 6),
      decoration: BoxDecoration(
        color: C.bubble,
        border: Border.all(color: highlighted ? C.muted : C.line),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          InkWell(
            onTap: onToggle,
            borderRadius: BorderRadius.circular(10),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
              child: Row(children: [
                Expanded(child: header),
                if (onToggle != null)
                  AnimatedRotation(
                    turns: open ? 0 : -0.25,
                    duration: const Duration(milliseconds: 150),
                    child: const Icon(Icons.expand_more, size: 16, color: C.muted),
                  ),
              ]),
            ),
          ),
          if (open)
            Container(
              decoration: const BoxDecoration(border: Border(top: BorderSide(color: C.line))),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              child: body,
            ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Composer: text box (Enter sends, Shift+Enter = new line, Esc stops), paperclip
// for files, and the send / stop button.

class Composer extends StatefulWidget {
  const Composer({
    super.key,
    required this.state,
    required this.enabled,
    required this.allowUploads,
    required this.placeholder,
  });

  final AppState state;
  final bool enabled;
  final bool allowUploads;
  final String placeholder;

  @override
  State<Composer> createState() => _ComposerState();
}

class _ComposerState extends State<Composer> {
  final _text = TextEditingController();
  final _focus = FocusNode();
  final List<PickedFile> _files = [];

  @override
  void initState() {
    super.initState();
    _text.addListener(() => setState(() {}));
    WidgetsBinding.instance.addPostFrameCallback((_) => _focus.requestFocus());
  }

  @override
  void dispose() {
    _text.dispose();
    _focus.dispose();
    super.dispose();
  }

  bool get _canSend => widget.enabled && (_text.text.trim().isNotEmpty || _files.isNotEmpty);

  void _submit() {
    if (!_canSend || widget.state.isStreaming) return;
    widget.state.send(_text.text, List.of(_files));
    _text.clear();
    setState(_files.clear);
    _focus.requestFocus();
  }

  Future<void> _pick() async {
    final picked = await openFiles(acceptedTypeGroups: [
      const XTypeGroup(label: 'Documents and images', extensions: uploadExtensions),
    ]);
    for (final f in picked) {
      final bytes = await f.readAsBytes();
      final dup = _files.any((x) => x.name == f.name && x.bytes.length == bytes.length);
      if (!dup) _files.add(PickedFile(name: f.name, bytes: bytes));
    }
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final streaming = widget.state.isStreaming;
    return Container(
      decoration: BoxDecoration(
        color: C.ground,
        border: Border.all(color: C.line),
        borderRadius: BorderRadius.circular(12),
        boxShadow: const [
          BoxShadow(color: Color(0x0A0A0A0A), blurRadius: 2, offset: Offset(0, 1)),
          BoxShadow(color: Color(0x0D0A0A0A), blurRadius: 14, offset: Offset(0, 4)),
        ],
      ),
      child: Column(
        children: [
          if (_files.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 12, 12, 0),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Wrap(spacing: 8, runSpacing: 8, children: [
                  for (final f in _files)
                    Container(
                      padding: const EdgeInsets.fromLTRB(6, 4, 2, 4),
                      decoration: BoxDecoration(
                        color: C.bubble,
                        border: Border.all(color: C.line),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Row(mainAxisSize: MainAxisSize.min, children: [
                        f.isImage
                            ? ClipRRect(
                                borderRadius: BorderRadius.circular(4),
                                child: Image.memory(f.bytes, width: 32, height: 32, fit: BoxFit.cover),
                              )
                            : const Icon(Icons.insert_drive_file_outlined, size: 14, color: C.muted),
                        const SizedBox(width: 6),
                        ConstrainedBox(
                          constraints: const BoxConstraints(maxWidth: 180),
                          child: Text(f.name,
                              maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12)),
                        ),
                        IconBtn(
                          icon: Icons.close,
                          tooltip: 'Remove',
                          size: 13,
                          onPressed: () => setState(() => _files.remove(f)),
                        ),
                      ]),
                    ),
                ]),
              ),
            ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                if (widget.allowUploads)
                  IconBtn(
                    icon: Icons.attach_file,
                    tooltip: 'Attach a file (CSV, PDF, Excel, Word, or an image)',
                    onPressed: widget.enabled ? _pick : null,
                  ),
                Expanded(
                  child: CallbackShortcuts(
                    bindings: {
                      const SingleActivator(LogicalKeyboardKey.enter): _submit,
                      const SingleActivator(LogicalKeyboardKey.numpadEnter): _submit,
                      const SingleActivator(LogicalKeyboardKey.escape): () {
                        if (streaming) widget.state.stop();
                      },
                    },
                    child: TextField(
                      controller: _text,
                      focusNode: _focus,
                      enabled: widget.enabled,
                      minLines: 1,
                      maxLines: 8,
                      keyboardType: TextInputType.multiline,
                      style: const TextStyle(fontSize: 15, height: 1.5),
                      decoration: InputDecoration(
                        hintText: widget.placeholder,
                        hintStyle: const TextStyle(color: C.muted),
                        border: InputBorder.none,
                        isDense: true,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 6, vertical: 8),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 6),
                _RoundButton(
                  icon: streaming ? Icons.stop_rounded : Icons.arrow_upward,
                  tooltip: streaming ? 'Stop (Esc)' : 'Send',
                  onPressed: streaming ? widget.state.stop : (_canSend ? _submit : null),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _RoundButton extends StatelessWidget {
  const _RoundButton({required this.icon, required this.tooltip, this.onPressed});

  final IconData icon;
  final String tooltip;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return IconButton.filled(
      onPressed: onPressed,
      tooltip: tooltip,
      icon: Icon(icon, size: 18),
      style: IconButton.styleFrom(
        backgroundColor: C.ink,
        foregroundColor: C.ground,
        disabledBackgroundColor: C.line,
        disabledForegroundColor: C.muted,
        fixedSize: const Size(36, 36),
        minimumSize: const Size(36, 36),
      ),
    );
  }
}
