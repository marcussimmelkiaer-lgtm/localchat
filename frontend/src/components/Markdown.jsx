import { useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import CodeBlock from './CodeBlock'

// Renders assistant markdown. Fenced code blocks route to <CodeBlock> (which
// stays plain mono while `streaming` and highlights on completion); inline code
// renders as a styled <code>.
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
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content || ''}
      </ReactMarkdown>
    </div>
  )
}
