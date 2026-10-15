import 'package:flutter_test/flutter_test.dart';
import 'package:localchat/text.dart';

void main() {
  group('splitThinking', () {
    test('no thinking', () {
      final t = splitThinking('Hello');
      expect(t.thinking, isNull);
      expect(t.answer, 'Hello');
    });

    test('one finished block', () {
      final t = splitThinking('<think>plan</think>\nAnswer');
      expect(t.thinking, 'plan');
      expect(t.answer, '\nAnswer');
      expect(t.thinkingDone, isTrue);
    });

    test('still thinking', () {
      final t = splitThinking('<think>half');
      expect(t.thinking, 'half');
      expect(t.thinkingDone, isFalse);
    });

    test('several blocks (thinks again after a tool call)', () {
      final t = splitThinking('<think>a</think>Let me check.<think>b</think>Done');
      expect(t.thinking, 'a\n\n---\n\nb');
      expect(t.answer, 'Let me check.Done');
    });

    test('empty finished block shows no box', () {
      expect(splitThinking('<think>\n\n</think>Hi').thinking, isNull);
    });
  });

  group('normalizeMath', () {
    test('inline dollars become \\( \\)', () {
      expect(normalizeMath(r'so $x^2$ grows'), r'so \(x^2\) grows');
    });

    test('display dollars become \\[ \\]', () {
      expect(normalizeMath(r'$$a+b$$'), '\n\\[\na+b\n\\]\n');
    });

    test('prices are left alone', () {
      const s = r'It costs $5 or $1,200. Total $59,334.';
      expect(normalizeMath(s), s);
    });

    test('code is left alone', () {
      const s = r'run `echo $HOME$` now';
      expect(normalizeMath(s), s);
    });
  });
}
