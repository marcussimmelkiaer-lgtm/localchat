// Text helpers for assistant output.

/// A reasoning model's output split into its `<think>` blocks and the answer.
class Thinking {
  const Thinking(this.thinking, this.answer, this.thinkingDone);

  /// All thought blocks joined by a rule, or null when there is nothing to show.
  final String? thinking;
  final String answer;

  /// False while the last `<think>` block is still streaming (no closing tag yet).
  final bool thinkingDone;
}

/// After a tool call Qwen3 thinks again, so there can be several blocks; they
/// are shown together, separated by a rule.
Thinking splitThinking(String content) {
  final thoughts = <String>[];
  final answer = StringBuffer();
  var rest = content;
  var done = true;
  while (true) {
    final open = rest.indexOf('<think>');
    if (open == -1) {
      answer.write(rest);
      break;
    }
    answer.write(rest.substring(0, open));
    rest = rest.substring(open + 7);
    final close = rest.indexOf('</think>');
    if (close == -1) {
      thoughts.add(rest);
      done = false;
      break;
    }
    thoughts.add(rest.substring(0, close));
    rest = rest.substring(close + 8);
  }
  final text = thoughts.map((t) => t.trim()).where((t) => t.isNotEmpty).join('\n\n---\n\n');
  final thinking = thoughts.isEmpty || (text.isEmpty && done) ? null : text;
  return Thinking(thinking, answer.toString(), done);
}

final _code = RegExp(r'(```[\s\S]*?(?:```|$)|`[^`\n]*`)');
final _display = RegExp(r'\$\$([\s\S]+?)\$\$');
// $…$ that looks like maths, not money: no digit/space right after the opening
// $, no space right before the closing one, all on one line.
final _inline = RegExp(r'(^|[^\\$\w])\$(?![\s\d$])([^$\n]*?[^\s\\$])\$(?!\d)');

/// The Markdown renderer understands \( … \) and \[ … \]. Models also write
/// $…$ and $$…$$; convert those, but leave prices ("$5", "$1,200") and code
/// alone.
String normalizeMath(String content) {
  if (!content.contains(r'$')) return content;
  final out = StringBuffer();
  var last = 0;
  for (final m in _code.allMatches(content)) {
    out.write(_fixMath(content.substring(last, m.start)));
    out.write(m.group(0));
    last = m.end;
  }
  out.write(_fixMath(content.substring(last)));
  return out.toString();
}

String _fixMath(String text) => text
    .replaceAllMapped(_display, (m) => '\n\\[\n${m.group(1)!.trim()}\n\\]\n')
    .replaceAllMapped(_inline, (m) => '${m.group(1)}\\(${m.group(2)}\\)');
