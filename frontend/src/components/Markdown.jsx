import { useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import CodeBlock from './CodeBlock'
import { normalizeMath } from '../lib/math'

const remarkPlugins = [remarkGfm, remarkMath]
// Bad or half-streamed LaTeX renders as red source text instead of throwing.
const rehypePlugins = [[rehypeKatex, { throwOnError: false, strict: 'ignore' }]]

// Renders assistant markdown. Fenced code blocks route to <CodeBlock> (which
// stays plain mono while `streaming` and highlights on completion); inline code
// renders as a styled <code>. Maths ($…$, $$…$$, \(…\), \[…\]) renders with KaTeX.
export default function Markdown({ content, streaming }) {
  const components = useMemo(
    () => ({
      // Unwrap <pre> so our CodeBlock isn't nested inside a <pre>.
      pre: ({ children }) => <>{children}</>,
      code({ className, children, ...props }) {
        const match = /language-(\w+)/.exec(className || '')
        const raw = (Array.isArray(children) ? children.join('') : String(children ?? '')).replace(
          /\n$/,
          ''
        )
        const isBlock = !!match || raw.includes('\n')
        if (isBlock) {
          return <CodeBlock code={raw} language={match?.[1]} streaming={streaming} />
        }
        return (
          <code className={className} {...props}>
            {children}
          </code>
        )
      },
      a: (props) => <a target="_blank" rel="noreferrer" {...props} />,
    }),
    [streaming]
  )

  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={remarkPlugins}
        rehypePlugins={rehypePlugins}
        components={components}
      >
        {normalizeMath(content)}
      </ReactMarkdown>
    </div>
  )
}
