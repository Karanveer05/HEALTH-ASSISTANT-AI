import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, setToken } from '../api'
import { useAuth } from '../App.jsx'

export default function Login() {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const { setUser } = useAuth()
  const navigate = useNavigate()

  async function submit(e) {
    e.preventDefault()
    setError(''); setBusy(true)
    try {
      const r = await api(`/auth/${mode}`, { method: 'POST', body: { email, password } })
      setToken(r.token)
      setUser({ email: r.email, has_profile: r.has_profile })
      navigate(r.has_profile ? '/' : '/profile')
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  return (
    <main className="container narrow">
      <div className="card hero">
        <h1>AI healthcare assistance</h1>
        <p>Describe your symptoms, answer a few smart follow-up questions, upload lab reports, and get possible causes,
          risk level, medicine information for your doctor, a 7-day diet plan and medicine price comparison.</p>
      </div>
      <form className="card" onSubmit={submit}>
        <h2>{mode === 'login' ? 'Log in' : 'Create your account'}</h2>
        <label htmlFor="email">Email</label>
        <input id="email" type="email" value={email} onChange={e => setEmail(e.target.value)} required autoComplete="email" />
        <label htmlFor="pw">Password</label>
        <input id="pw" type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={mode === 'register' ? 8 : 1}
          autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />
        {mode === 'register' && <p className="hint">At least 8 characters.</p>}
        {error && <p className="error">{error}</p>}
        <div className="row" style={{ marginTop: '1rem' }}>
          <button className="btn" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Log in' : 'Create account'}</button>
          <button type="button" className="btn ghost" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}>
            {mode === 'login' ? 'New here? Create an account' : 'Have an account? Log in'}
          </button>
        </div>
      </form>
    </main>
  )
}
