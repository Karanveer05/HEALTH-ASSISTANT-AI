import { useEffect, useState } from 'react'
import { api, setToken } from '../api'
import { useAuth } from '../App.jsx'

export default function Privacy() {
  const [log, setLog] = useState(null)
  const [confirm, setConfirm] = useState('')
  const { logout } = useAuth()

  useEffect(() => { api('/audit').then(setLog).catch(() => setLog([])) }, [])

  async function deleteAccount() {
    await api('/account', { method: 'DELETE' })
    setToken(null)
    logout()
  }

  return (
    <main className="container narrow">
      <h1>Privacy and security</h1>
      <div className="card">
        <h2>How your data is protected</h2>
        <ul className="tight">
          <li>Your password is stored only as a bcrypt hash.</li>
          <li>Your profile, symptoms, answers, reports and results are encrypted in the database (Fernet / AES).</li>
          <li>Uploaded report files are encrypted on disk.</li>
          <li>You can only see your own records; every access is written to an audit log.</li>
          <li>Your login expires after 60 minutes and is cleared when you close the browser.</li>
        </ul>
      </div>
      <div className="card">
        <h2>Recent activity on your account</h2>
        {!log ? <div className="spinner" /> : (
          <div className="table-wrap"><table>
            <thead><tr><th>When</th><th>Action</th><th>Item</th><th>IP</th></tr></thead>
            <tbody>{log.map((r, i) => <tr key={i}><td className="small">{new Date(r.at).toLocaleString()}</td><td>{r.action.replace(/_/g, ' ')}</td><td className="small">{r.target}</td><td className="small">{r.ip}</td></tr>)}</tbody>
          </table></div>
        )}
      </div>
      <div className="card">
        <h2>Delete my account</h2>
        <p className="muted">This permanently deletes your profile, all health checks and uploaded reports.</p>
        <label htmlFor="confirm">Type DELETE to confirm</label>
        <input id="confirm" value={confirm} onChange={e => setConfirm(e.target.value)} />
        <button className="btn danger" style={{ marginTop: '.7rem' }} disabled={confirm !== 'DELETE'} onClick={deleteAccount}>Delete everything</button>
      </div>
    </main>
  )
}
