import { useEffect, useState } from 'react'
import { api } from '../api'

export default function EmergencyOverlay({ emergency, onClose }) {
  const [contact, setContact] = useState(null)

  useEffect(() => {
    api('/profile').then(p => p?.emergency_contact_phone && setContact(p)).catch(() => {})
  }, [])

  if (!emergency) return null
  const suicidal = emergency.guides.some(g => g.id === 'suicidal')

  return (
    <div className="sos-overlay" role="alertdialog" aria-modal="true" aria-labelledby="sos-title">
      <div className="sos-box">
        <h2 id="sos-title">This may be an emergency</h2>
        <p>Based on what you wrote, please get help now. Do not wait for the analysis.</p>
        <div className="sos-calls">
          {suicidal && <a className="btn danger big" href="tel:14416">Tele-MANAS 14416</a>}
          <a className="btn danger big" href="tel:112">Call 112</a>
          <a className="btn danger big" href="tel:108">Ambulance 108</a>
          {contact && <a className="btn secondary big" href={`tel:${contact.emergency_contact_phone}`}>Call {contact.emergency_contact_name || 'my contact'}</a>}
          <a className="btn secondary big" href="https://www.google.com/maps/search/hospital+near+me" target="_blank" rel="noreferrer">Nearest hospital</a>
        </div>
        {emergency.guides.map(g => (
          <div key={g.id} style={{ marginBottom: '.8rem' }}>
            <h3>{g.title}: what to do now</h3>
            {g.details && <p className="small"><b>Values:</b> {g.details.join(', ')}</p>}
            <ol className="steps-list">{g.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
            <p className="small muted">Source: <a href={g.source} target="_blank" rel="noreferrer">{g.source}</a></p>
          </div>
        ))}
        <button className="btn ghost" onClick={onClose}>I am safe, continue with the check</button>
      </div>
    </div>
  )
}
