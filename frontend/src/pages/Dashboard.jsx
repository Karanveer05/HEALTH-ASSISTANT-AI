import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'

const STATUS = { questions: 'Answering questions', report: 'Report needed', ready: 'Ready to analyse', analyzed: 'Report ready' }

export default function Dashboard() {
  const [cases, setCases] = useState(null)
  const [health, setHealth] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api('/cases').then(setCases).catch(e => setError(e.message))
    api('/health').then(setHealth).catch(() => {})
  }, [])

  return (
    <main className="container">
      <div className="card hero">
        <h1>How are you feeling today?</h1>
        <p>Start a health check: describe the problem, answer follow-up questions, add a lab report if needed, and get your report.</p>
        <Link to="/new" className="btn big">Start a new health check</Link>
      </div>

      {health && health.llm === 'offline' && (
        <div className="alert warn small">
          AI model not connected: the app is using its built-in rule engine. Add a free Gemini or Groq API key in <code>backend/.env</code> for smarter questions and analysis.
        </div>
      )}

      <div className="card">
        <h2>Your health checks</h2>
        {error && <p className="error">{error}</p>}
        {!cases ? <div className="spinner" /> : cases.length === 0 ? <p className="muted">No checks yet.</p> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>#</th><th>Problem</th><th>Status</th><th>Risk</th><th>Most likely</th><th>Date</th></tr></thead>
              <tbody>
                {cases.map(c => (
                  <tr key={c.id}>
                    <td>{c.id}</td>
                    <td><Link to={`/cases/${c.id}`}>{c.complaint}</Link></td>
                    <td>{STATUS[c.status] || c.status}</td>
                    <td>{c.risk ? <span className={`badge b-${c.risk}`}>{c.risk}</span> : '-'}</td>
                    <td>{c.top_condition || '-'}</td>
                    <td className="small muted">{new Date(c.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  )
}
