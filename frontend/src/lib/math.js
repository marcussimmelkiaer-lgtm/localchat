// Prepares model output for remark-math. Models write maths in several styles;
// remark-math only understands $…$ and $$…$$, so:
//   \[ … \] and $$ … $$  ->  a display block, with $$ on lines of their own
//                            (otherwise "text $$x$$" renders inline)
//   \( … \)  ->  inline $ … $
//   "$5", "$1,200." ->  \$ (currency, so two prices on a line don't become maths)
// Code blocks and inline code are left untouched.

const CODE = /(```[\s\S]*?(?:```|$)|`[^`\n]*`)/g
const DISPLAY = /\\\[([\s\S]+?)\\\]|\$\$([\s\S]+?)\$\$/g
const INLINE = /\\\(([\s\S]+?)\\\)/g
const CURRENCY = /(^|[^\\$])\$(?=\d[\d,]*(?:\.\d+)?(?:$|[\s.,;:!?)%*\]~]|(?:k|K|m|M|bn|B)\b))/gm

function fixMath(text) {
  return text
    // Function replacements are literal (no "$" patterns); the string one uses
    // $1 = the preceding character and $$ = a literal "$".
    .replace(DISPLAY, (_, a, b) => `\n\n$$\n${(a ?? b).trim()}\n$$\n\n`)
    .replace(INLINE, (_, body) => `$${body.trim()}$`)
    .replace(CURRENCY, '$1\\$$')
}

export function normalizeMath(content) {
  if (!content || (!content.includes('\\') && !content.includes('$'))) return content || ''
  return content
    .split(CODE)
    .map((part, i) => (i % 2 === 1 ? part : fixMath(part)))
    .join('')
}
