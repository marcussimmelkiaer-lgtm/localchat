import { Component } from 'react'

// Catches any render error so the whole app never blanks out. Shows a quiet,
// monochrome fallback with the error message and a reload button.
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // Surface for debugging; the fallback UI stays up regardless.
    console.error('Render error:', error, info)
  }

  render() {
    if (!this.state.error) return this.props.children
    const msg = this.state.error?.message || String(this.state.error)
    return (
      <div className="flex h-full w-full items-center justify-center bg-ground-2 px-6 text-center">
        <div className="max-w-md">
          <h1 className="text-[18px] font-semibold text-ink">Something went wrong</h1>
          <p className="mt-2 break-words text-[13px] text-muted">{msg}</p>
          <button
            onClick={() => window.location.reload()}
            className="focus-ring mt-5 rounded-control border border-line px-3 py-2 text-[13px] font-medium text-ink transition hover:bg-hover"
          >
            Reload
          </button>
        </div>
      </div>
    )
  }
}
