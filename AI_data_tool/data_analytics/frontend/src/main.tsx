import React from 'react'
import ReactDOM from 'react-dom/client'
import { Toaster } from 'react-hot-toast'
import App from './App'
import './index.css'

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
    <Toaster position="bottom-right" toastOptions={{ style: { background: 'var(--surface2)', color: 'var(--text)', border: '1px solid var(--border)' } }} />
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
