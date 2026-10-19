import { useEffect, useState } from 'react'
import { api } from '../api'

export default function EmergencyPage() {
  const [data, setData] = useState(null)
  const [open, setOpen] = useState(null)

  useEffect(() => { api('/emergency').then(setData).catch(() => {}) }, [])

  return (
    <main className="container narrow">
      <div className="card" style={{ borderTop: '6px solid var(--bad)' }}>
        <h1 style={{ color: 'var(--bad)' }}>Emergency help</h1>
        <p>If someone's life may be in danger, call now. Do not wait for the app.</p>
        <div className="sos-calls">
          <a className="btn danger big" href="tel:112">Call 112</a>
          <a className="btn danger big" href="tel:108">Ambulance 108</a>
          <a className="btn secondary big" href="https://www.google.com/maps/search/hospital+near+me" target="_blank" rel="noreferrer">Nearest hospital</a>
        </div>
        <p className="small muted">Mental health support: Tele-MANAS <a href="tel:14416">14416</a> (free, 24x7).</p>
      </div>
      <h2>First aid: what to do</h2>
      {!data ? <div className="spinner" /> : data.guides.map(g => (
        <div className="card" key={g.id}>
          <button className="btn ghost" style={{ width: '100%', justifyContent: 'space-between' }} onClick={() => setOpen(open === g.id ? null : g.id)}>
            <span>{g.title}</span><span>{open === g.id ? '−' : '+'}</span>
          </button>
          {open === g.id && (
            <>
              <ol className="steps-list">{g.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
              <p className="small muted">Source: <a href={g.source} target="_blank" rel="noreferrer">{g.source}</a></p>
            </>
          )}
        </div>
      ))}
    </main>
  )
}
