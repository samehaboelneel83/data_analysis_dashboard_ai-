import React from 'react'
import ReactDOM from 'react-dom/client'
import { Toaster } from 'react-hot-toast'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
    <Toaster position="bottom-right" toastOptions={{ style: { background: 'var(--surface2)', color: 'var(--text)', border: '1px solid var(--border)' } }} />
  </React.StrictMode>,
)
