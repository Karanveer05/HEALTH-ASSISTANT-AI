import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'

export default function NewCase() {
  const [f, setF] = useState({ complaint: '', duration: '', severity: 5, other_symptoms: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()
  const set = k => e => setF({ ...f, [k]: e.target.value })

  async function submit(e) {
    e.preventDefault()
    setError(''); setBusy(true)
    try {
      const c = await api('/cases', { method: 'POST', body: { ...f, severity: Number(f.severity) } })
      navigate(`/cases/${c.id}`, { state: { emergency: c.new_emergency } })
    } catch (err) { setError(err.message); setBusy(false) }
  }

  return (
    <main className="container narrow">
      <h1>New health check</h1>
      <form className="card" onSubmit={submit}>
        <label htmlFor="complaint">What is the main problem?</label>
        <textarea id="complaint" value={f.complaint} onChange={set('complaint')} required minLength={3}
          placeholder="e.g. Fever since 3 days with body ache and headache" />
        <div className="grid grid-2">
          <div>
            <label htmlFor="duration">Since when?</label>
            <input id="duration" value={f.duration} onChange={set('duration')} placeholder="e.g. 3 days, 2 weeks" />
          </div>
          <div>
            <label htmlFor="sev">How bad is it? <b>{f.severity}/10</b></label>
            <input id="sev" type="range" min="1" max="10" value={f.severity} onChange={set('severity')} />
            <div className="row spread small muted"><span>Mild</span><span>Worst</span></div>
          </div>
        </div>
        <label htmlFor="other">Any other symptoms?</label>
        <textarea id="other" value={f.other_symptoms} onChange={set('other_symptoms')} placeholder="e.g. loss of appetite, nausea" />
        <div className="alert bad small">
          If you have chest pain, difficulty breathing, signs of stroke, heavy bleeding or fainting, call <a href="tel:112">112</a> / <a href="tel:108">108</a> now.
        </div>
        {error && <p className="error">{error}</p>}
        <button className="btn big" disabled={busy}>{busy ? 'Thinking…' : 'Continue'}</button>
      </form>
    </main>
  )
}
