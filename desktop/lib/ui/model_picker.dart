// "Models" dialog: curated catalog + other downloaded models (use / download /
// delete, with progress), and a free-form Hugging Face download field.

import 'package:flutter/material.dart';

import '../models.dart';
import '../state.dart';
import 'theme.dart';

Future<void> showModelPicker(BuildContext context, AppState state) {
  state.refreshModels();
  return showDialog<void>(
    context: context,
    barrierColor: const Color(0x330A0A0A),
    builder: (_) => ListenableBuilder(listenable: state, builder: (_, _) => _ModelPicker(state: state)),
  );
}

class _ModelPicker extends StatefulWidget {
  const _ModelPicker({required this.state});

  final AppState state;

  @override
  State<_ModelPicker> createState() => _ModelPickerState();
}

class _ModelPickerState extends State<_ModelPicker> {
  final _spec = TextEditingController();
  String? _confirmDelete; // path pending delete confirmation

  @override
  void dispose() {
    _spec.dispose();
    super.dispose();
  }

  void _download() {
    final s = _spec.text.trim();
    if (s.isEmpty || widget.state.task.busy) return;
    widget.state.downloadModel(s).then((_) {
      if (widget.state.modelActionError == null) _spec.clear();
    });
  }

  @override
  Widget build(BuildContext context) {
    final st = widget.state;
    final task = st.task;
    final list = st.models;
    final target = task.target;
    final rows = <Widget>[];

    bool targets(ModelEntry e) => task.busy && target != null && (target == e.spec || target == e.path);
    final matched = list != null &&
        [...list.catalog, ...list.custom].any((e) => target != null && (target == e.spec || target == e.path));
    if (task.busy && target != null && !matched) {
      // A custom download has no row until it finishes; show one for its progress.
      rows.add(_ModelRow(
        entry: ModelEntry(
          title: target.split(RegExp(r'[\\/]')).last.replaceAll(RegExp(r'\.gguf$', caseSensitive: false), ''),
          subtitle: 'Custom download',
          path: null,
        ),
        task: task,
        targeted: true,
        busy: true,
      ));
    }
    for (final e in list?.catalog ?? const <ModelEntry>[]) {
      rows.add(_row(e, targets(e)));
    }
    if ((list?.custom ?? const []).isNotEmpty) {
      rows.add(const Padding(
        padding: EdgeInsets.fromLTRB(4, 12, 4, 4),
        child: Text('OTHER DOWNLOADED',
            style: TextStyle(fontSize: 11, fontWeight: FontWeight.w500, letterSpacing: 0.5, color: C.muted)),
      ));
      for (final e in list!.custom) {
        rows.add(_row(e, targets(e)));
      }
    }

    final error = st.modelActionError ?? (task.status == 'error' ? task.error : null);

    return Dialog(
      backgroundColor: C.ground,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12), side: const BorderSide(color: C.line)),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 460, maxHeight: 620),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              padding: const EdgeInsets.fromLTRB(16, 10, 8, 10),
              decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: C.line))),
              child: Row(
                children: [
                  const Expanded(
                    child: Text('Models', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                  ),
                  IconBtn(icon: Icons.close, tooltip: 'Close', onPressed: () => Navigator.of(context).pop()),
                ],
              ),
            ),
            Flexible(
              child: ListView(
                shrinkWrap: true,
                padding: const EdgeInsets.all(12),
                children: [
                  if (error != null)
                    Container(
                      margin: const EdgeInsets.only(bottom: 12),
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      decoration: BoxDecoration(
                        color: C.bubble,
                        border: Border.all(color: C.line),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(child: Text(error, style: const TextStyle(fontSize: 12.5, color: C.muted))),
                          if (st.modelActionError != null)
                            InkWell(onTap: st.clearModelError, child: const Icon(Icons.close, size: 14, color: C.muted)),
                        ],
                      ),
                    ),
                  if (list == null)
                    const Padding(
                      padding: EdgeInsets.all(16),
                      child: Center(child: Text('Loading…', style: TextStyle(color: C.muted, fontSize: 12.5))),
                    ),
                  ...rows,
                ],
              ),
            ),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: const BoxDecoration(border: Border(top: BorderSide(color: C.line))),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Padding(
                    padding: EdgeInsets.only(left: 4, bottom: 6),
                    child: Text('DOWNLOAD FROM HUGGING FACE',
                        style: TextStyle(fontSize: 11, fontWeight: FontWeight.w500, letterSpacing: 0.5, color: C.muted)),
                  ),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _spec,
                          enabled: !task.busy,
                          onSubmitted: (_) => _download(),
                          style: const TextStyle(fontSize: 12.5),
                          decoration: InputDecoration(
                            hintText: 'Qwen/Qwen3-0.6B',
                            isDense: true,
                            contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                            enabledBorder: OutlineInputBorder(
                              borderSide: const BorderSide(color: C.line),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            focusedBorder: OutlineInputBorder(
                              borderSide: const BorderSide(color: C.muted),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            disabledBorder: OutlineInputBorder(
                              borderSide: const BorderSide(color: C.line),
                              borderRadius: BorderRadius.circular(8),
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      ListenableBuilder(
                        listenable: _spec,
                        builder: (_, _) => _InkButton(
                          label: 'Download',
                          onPressed: task.busy || _spec.text.trim().isEmpty ? null : _download,
                        ),
                      ),
                    ],
                  ),
                  const Padding(
                    padding: EdgeInsets.only(left: 4, top: 6),
                    child: Text(
                      'Paste a repo id (Qwen/Qwen3-0.6B), add :Q5_K_M to pick a quant, '
                      'or paste a full owner/repo/file.gguf / Hugging Face URL.',
                      style: TextStyle(fontSize: 11, color: C.muted),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _row(ModelEntry e, bool targeted) {
    final st = widget.state;
    return _ModelRow(
      entry: e,
      task: st.task,
      targeted: targeted,
      busy: st.task.busy,
      confirming: e.path != null && _confirmDelete == e.path,
      onUse: e.path == null ? null : () => st.switchModel(e.path!),
      // A vision model needs its mmproj too and shouldn't become the default
      // (image turns borrow it automatically): download both, don't switch.
      onDownload: e.spec == null
          ? null
          : () => e.projection != null
              ? st.downloadModel(e.spec!, thenSwitch: false, extra: [e.projection!])
              : st.downloadModel(e.spec!),
      onAskDelete: () => setState(() => _confirmDelete = e.path),
      onCancelDelete: () => setState(() => _confirmDelete = null),
      onConfirmDelete: () {
        setState(() => _confirmDelete = null);
        if (e.path != null) st.deleteModel(e.path!);
      },
    );
  }
}

class _ModelRow extends StatelessWidget {
  const _ModelRow({
    required this.entry,
    required this.task,
    required this.targeted,
    required this.busy,
    this.confirming = false,
    this.onUse,
    this.onDownload,
    this.onAskDelete,
    this.onCancelDelete,
    this.onConfirmDelete,
  });

  final ModelEntry entry;
  final ModelTask task;
  final bool targeted;
  final bool busy;
  final bool confirming;
  final VoidCallback? onUse;
  final VoidCallback? onDownload;
  final VoidCallback? onAskDelete;
  final VoidCallback? onCancelDelete;
  final VoidCallback? onConfirmDelete;

  @override
  Widget build(BuildContext context) {
    final downloading = task.status == 'downloading';
    final pct = (task.fraction * 100).round();
    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(border: Border.all(color: C.line), borderRadius: BorderRadius.circular(8)),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(entry.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500)),
                Text(entry.subtitle,
                    maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 11.5, color: C.muted)),
                if (targeted) ...[
                  const SizedBox(height: 6),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(4),
                    child: LinearProgressIndicator(
                      value: downloading ? task.fraction : null,
                      minHeight: 4,
                      color: C.ink,
                      backgroundColor: C.bubbleHover,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(downloading ? 'Downloading… $pct%' : 'Loading…',
                      style: const TextStyle(fontSize: 11, color: C.muted)),
                ],
              ],
            ),
          ),
          if (!targeted) ...[
            const SizedBox(width: 8),
            if (entry.active)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(color: C.bubble, borderRadius: BorderRadius.circular(8)),
                child: const Row(mainAxisSize: MainAxisSize.min, children: [
                  Icon(Icons.check, size: 13),
                  SizedBox(width: 4),
                  Text('Active', style: TextStyle(fontSize: 11.5, fontWeight: FontWeight.w500)),
                ]),
              )
            else if (entry.downloaded)
              OutlinedButton(
                onPressed: busy ? null : onUse,
                style: OutlinedButton.styleFrom(
                  foregroundColor: C.ink,
                  side: const BorderSide(color: C.line),
                  visualDensity: VisualDensity.compact,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                  textStyle: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500),
                ),
                child: const Text('Use'),
              )
            else
              _InkButton(label: 'Download', onPressed: busy ? null : onDownload, compact: true),
            if (entry.downloaded && !entry.active)
              confirming
                  ? Row(mainAxisSize: MainAxisSize.min, children: [
                      TextButton(
                        onPressed: busy ? null : onConfirmDelete,
                        style: TextButton.styleFrom(foregroundColor: C.ink, visualDensity: VisualDensity.compact),
                        child: const Text('Delete', style: TextStyle(fontSize: 11.5)),
                      ),
                      TextButton(
                        onPressed: onCancelDelete,
                        style: TextButton.styleFrom(foregroundColor: C.muted, visualDensity: VisualDensity.compact),
                        child: const Text('Cancel', style: TextStyle(fontSize: 11.5)),
                      ),
                    ])
                  : IconBtn(
                      icon: Icons.delete_outline,
                      tooltip: 'Delete from disk',
                      size: 16,
                      onPressed: busy ? null : onAskDelete,
                    ),
          ],
        ],
      ),
    );
  }
}

class _InkButton extends StatelessWidget {
  const _InkButton({required this.label, this.onPressed, this.compact = false});

  final String label;
  final VoidCallback? onPressed;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    return FilledButton(
      onPressed: onPressed,
      style: FilledButton.styleFrom(
        backgroundColor: C.ink,
        foregroundColor: C.ground,
        disabledBackgroundColor: C.line,
        disabledForegroundColor: C.muted,
        visualDensity: compact ? VisualDensity.compact : VisualDensity.standard,
        padding: EdgeInsets.symmetric(horizontal: 12, vertical: compact ? 0 : 16),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        textStyle: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w500),
      ),
      child: Text(label),
    );
  }
}
