import { useState, type FormEvent } from 'react'
import { useAuth } from '../contexts/AuthContext'
import toast from 'react-hot-toast'

export default function Login() {
  const { login, user } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (user) {
    // Already authenticated (e.g. navigated back to /login manually) — bounce home.
    window.location.replace('/')
    return null
  }

  const inp = {
    style: {
      width: '100%', fontSize: 13, padding: '8px 10px', boxSizing: 'border-box' as const,
      background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text)',
    },
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!email.trim() || !password) {
      toast.error('Email and password are required')
      return
    }
    setSubmitting(true)
    try {
      await login(email.trim(), password)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? 'Invalid email or password')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg)' }}>
      <form onSubmit={handleSubmit} style={{
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 12, padding: 32, width: 360,
      }}>
        <div style={{ fontWeight: 800, fontSize: 20, color: 'var(--accent)', marginBottom: 24, textAlign: 'center' }}>
          Datalytics
        </div>
        <label style={{ display: 'block', marginBottom: 14 }}>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 5 }}>Email</div>
          <input type="email" value={email} onChange={e => setEmail(e.target.value)} autoFocus {...inp} />
        </label>
        <label style={{ display: 'block', marginBottom: 20 }}>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 5 }}>Password</div>
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} {...inp} />
        </label>
        <button type="submit" className="btn btn-primary" disabled={submitting} style={{ width: '100%' }}>
          {submitting ? 'Signing in…' : 'Sign In'}
        </button>
      </form>
    </div>
  )
}
