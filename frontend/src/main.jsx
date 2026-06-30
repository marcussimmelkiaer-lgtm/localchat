import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import './index.css'

// No StrictMode: it double-invokes effects in dev, which interferes with the
// streaming/AbortController lifecycle. The production bundle (served in the
// pywebview window) never runs StrictMode anyway, so dev mirrors prod.
ReactDOM.createRoot(document.getElementById('root')).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>
)
