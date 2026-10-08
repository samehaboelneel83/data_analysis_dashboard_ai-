import React from 'react'
import ReactDOM from 'react-dom/client'
import toast, { Toaster } from 'react-hot-toast'

// One toast per message. Two requests failing for the same reason (a schema
// browse and its first preview, say) used to stack the identical error twice;
// react-hot-toast replaces a toast that shares an id instead of adding one.
const showError = toast.error
toast.error = ((message, opts) =>
  showError(message, { id: typeof message === 'string' ? `err:${message}` : undefined, ...opts })) as typeof toast.error
import App from './App'
import './index.css'
import { installAutoDir } from './lib/autoDir'
import { installDisplayLocale } from './lib/displayLocale'

// Latin values in RTL form controls were clipped at their start (QA 2026-09-26).
installAutoDir()

// Dates and numbers in the interface language, not the operating system's
// (see lib/displayLocale). The switcher keeps it in step afterwards.
try {
  installDisplayLocale(localStorage.getItem('datalytics.language') === 'ar' ? 'ar' : 'en')
} catch { installDisplayLocale('en') }

// Stamp the theme BEFORE first paint, so pages outside the shell (Login, the
// shared/embed views) render in the product's blue/white light default rather
// than the token file's dark base. Layout owns the toggle afterwards and
// writes the same attribute + storage key.
try {
  const stored = localStorage.getItem('theme')
  document.documentElement.setAttribute(
    'data-theme', stored === 'dark' || stored === 'light' ? stored : 'light')
} catch { document.documentElement.setAttribute('data-theme', 'light') }

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
    {/* QA3 B6: above the builder's status bar, never over its Shortcuts link
        (index.css raises --dl-toast-bottom while one is on the page). */}
    <Toaster position="bottom-right" containerStyle={{ bottom: 'var(--dl-toast-bottom, 16px)' }} toastOptions={{ style: {
      background: 'var(--surface)', color: 'var(--text)', border: '1px solid var(--border)',
      borderRadius: 'var(--dl-radius-card)', boxShadow: 'var(--dl-shadow-overlay)',
      fontSize: 'var(--dl-text-data)', padding: '10px 14px' } }} />
  </React.StrictMode>,
)

// Register the service worker in production only. Under `vite dev` it would sit in
// front of the HMR websocket and asset requests, which breaks hot reload — and it
// buys nothing locally, since installability is a deployed-app concern.
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // A failed registration only costs installability and offline fallback; the
      // app itself works fine without it, so there is nothing to surface here.
    })
  })
}
