// Left column: logo, New chat, the conversation list, and the model button.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models.dart';
import '../state.dart';
import 'model_picker.dart';
import 'theme.dart';

class Sidebar extends StatelessWidget {
  const Sidebar({super.key, required this.state, required this.onCollapse});

  final AppState state;
  final VoidCallback onCollapse;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 260,
      decoration: const BoxDecoration(
        color: C.ground2,
        border: Border(right: BorderSide(color: C.line)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 14, 12, 4),
            child: Align(
              alignment: Alignment.centerLeft,
              child: Image.asset('assets/logo-nobodywho.png', height: 18),
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(8),
            child: Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: state.isStreaming ? null : () => state.newConversation(),
                    icon: const Icon(Icons.add, size: 16),
                    label: const Text('New chat'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: C.ink,
                      alignment: Alignment.centerLeft,
                      side: const BorderSide(color: C.line),
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                      textStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
                    ),
                  ),
                ),
                const SizedBox(width: 4),
                IconBtn(icon: Icons.view_sidebar_outlined, tooltip: 'Collapse sidebar', onPressed: onCollapse),
              ],
            ),
          ),
          Expanded(
            child: state.conversations.isEmpty
                ? const Padding(
                    padding: EdgeInsets.all(16),
                    child: Text('No conversations yet', style: TextStyle(fontSize: 12, color: C.muted)),
                  )
                : ListView.builder(
                    padding: const EdgeInsets.fromLTRB(8, 0, 8, 8),
                    itemCount: state.conversations.length,
                    itemBuilder: (_, i) {
                      final c = state.conversations[i];
                      return _ConversationItem(
                        key: ValueKey(c.id),
                        conv: c,
                        active: c.id == state.activeId,
                        state: state,
                      );
                    },
                  ),
          ),
          Container(
            decoration: const BoxDecoration(border: Border(top: BorderSide(color: C.line))),
            padding: const EdgeInsets.all(8),
            child: _ModelButton(state: state),
          ),
        ],
      ),
    );
  }
}

class _ConversationItem extends StatefulWidget {
  const _ConversationItem({super.key, required this.conv, required this.active, required this.state});

  final Conversation conv;
  final bool active;
  final AppState state;

  @override
  State<_ConversationItem> createState() => _ConversationItemState();
}

class _ConversationItemState extends State<_ConversationItem> {
  bool _hover = false;
  bool _editing = false;
  late final TextEditingController _ctrl = TextEditingController();
  final FocusNode _focus = FocusNode();

  @override
  void initState() {
    super.initState();
    _focus.addListener(() {
      if (!_focus.hasFocus && _editing) _commit();
    });
  }

  @override
  void dispose() {
    _ctrl.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _startEdit() {
    _ctrl.text = widget.conv.title;
    _ctrl.selection = TextSelection(baseOffset: 0, extentOffset: _ctrl.text.length);
    setState(() => _editing = true);
    WidgetsBinding.instance.addPostFrameCallback((_) => _focus.requestFocus());
  }

  void _commit() {
    final t = _ctrl.text.trim();
    setState(() => _editing = false);
    if (t.isNotEmpty && t != widget.conv.title) widget.state.rename(widget.conv.id, t);
  }

  @override
  Widget build(BuildContext context) {
    final bg = widget.active ? C.bubble : (_hover || _editing ? C.hover : Colors.transparent);
    return Padding(
      padding: const EdgeInsets.only(bottom: 2),
      child: MouseRegion(
        onEnter: (_) => setState(() => _hover = true),
        onExit: (_) => setState(() => _hover = false),
        cursor: SystemMouseCursors.click,
        child: GestureDetector(
          onTap: _editing ? null : () => widget.state.select(widget.conv.id),
          onDoubleTap: _startEdit,
          child: Container(
            height: 34,
            padding: const EdgeInsets.only(left: 8, right: 2),
            decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(8)),
            child: _editing
                ? CallbackShortcuts(
                    bindings: {
                      const SingleActivator(LogicalKeyboardKey.escape): () => setState(() => _editing = false),
                    },
                    child: TextField(
                      controller: _ctrl,
                      focusNode: _focus,
                      style: const TextStyle(fontSize: 13),
                      decoration: const InputDecoration(isDense: true, border: InputBorder.none),
                      onSubmitted: (_) => _commit(),
                    ),
                  )
                : Row(
                    children: [
                      Expanded(
                        child: Text(
                          widget.conv.title.isEmpty ? 'New chat' : widget.conv.title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 13, color: C.ink),
                        ),
                      ),
                      if (_hover) ...[
                        IconBtn(icon: Icons.edit_outlined, tooltip: 'Rename', size: 15, onPressed: _startEdit),
                        IconBtn(
                          icon: Icons.delete_outline,
                          tooltip: 'Delete',
                          size: 15,
                          onPressed: () => widget.state.delete(widget.conv.id),
                        ),
                      ],
                    ],
                  ),
          ),
        ),
      ),
    );
  }
}

class _ModelButton extends StatelessWidget {
  const _ModelButton({required this.state});

  final AppState state;

  @override
  Widget build(BuildContext context) {
    final name = state.models?.activeName?.replaceAll(RegExp(r'\.gguf$', caseSensitive: false), '') ?? 'No model';
    return OutlinedButton(
      onPressed: () => showModelPicker(context, state),
      style: OutlinedButton.styleFrom(
        foregroundColor: C.ink,
        side: const BorderSide(color: C.line),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      ),
      child: Row(
        children: [
          const Icon(Icons.memory, size: 15, color: C.muted),
          const SizedBox(width: 8),
          Expanded(
            child: Text(name, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12.5)),
          ),
          state.task.busy ? const PulseDot() : const Icon(Icons.expand_more, size: 16, color: C.muted),
        ],
      ),
    );
  }
}
