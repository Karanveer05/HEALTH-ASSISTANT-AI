import { useState } from 'react'
import { downloadPdf } from '../api'
import DietChart from './DietChart.jsx'
import PriceCompare from './PriceCompare.jsx'

const CONF = { low: 33, medium: 66, high: 100 }
const FOOD = { after: 'after food', before: 'before food', empty_stomach: 'on an empty stomach', any: 'with or without food' }
export const flagClass = f => (f === 'low' || f === 'high' ? `b-${f}-flag` : `b-${f}`)

export default function ResultView({ caseData, onRerun, busy }) {
  const r = caseData.result
  const [tab, setTab] = useState('overview')
  const [pdfBusy, setPdfBusy] = useState(false)
  const [error, setError] = useState('')
  const med = r.medication
  const tabs = [['overview', 'Possible causes'], ['labs', `Lab findings (${r.labs.length})`]]
  if (med) tabs.push(['meds', 'Medicines & schedule'])
  if (r.diet) tabs.push(['diet', '7-day diet chart'])
  if (med) tabs.push(['prices', 'Price comparison'])
  tabs.push(['report', 'Full report'])

  const priceSuggestions = med ? [...new Set(med.items.flatMap(m => [m.brands[0], m.name.split(' (')[0]]))].slice(0, 6) : []

  async function pdf() {
    setPdfBusy(true); setError('')
    try { await downloadPdf(caseData.id) } catch (e) { setError(e.message) } finally { setPdfBusy(false) }
  }

  return (
    <div>
      <div className="card" style={{ borderLeft: `6px solid var(--${r.risk.level === 'low' ? 'ok' : r.risk.level === 'moderate' ? 'warn' : 'bad'})` }}>
        <div className="row spread">
          <div>
            <span className={`badge b-${r.risk.level}`}>Risk: {r.risk.level}</span>
            <h2 style={{ marginTop: '.4rem' }}>{r.risk.advice}</h2>
          </div>
          <div className="row no-print">
            <button className="btn" onClick={pdf} disabled={pdfBusy}>{pdfBusy ? 'Preparing…' : 'Download PDF report'}</button>
            <button className="btn secondary" onClick={onRerun} disabled={busy}>{busy ? 'Analysing…' : 'Re-run analysis'}</button>
          </div>
        </div>
        <ul className="tight small">{r.risk.reasons.map((x, i) => <li key={i}>{x}</li>)}</ul>
        {error && <p className="error">{error}</p>}
        <p className="small muted">{r.disclaimer} · Engine: {r.engine.llm === 'offline' ? 'built-in rules' : r.engine.llm} + {r.engine.rag} search</p>
      </div>

      <div className="tabs no-print">
        {tabs.map(([k, l]) => <button key={k} className={`tab ${tab === k ? 'on' : ''}`} onClick={() => setTab(k)}>{l}</button>)}
      </div>

      {tab === 'overview' && (
        <div className="card">
          <p>{r.analysis.summary}</p>
          {r.analysis.conditions.map((c, i) => (
            <div className="cond" key={i}>
              <div className="row spread"><h3>{i + 1}. {c.name}</h3><span className={`badge b-${c.confidence}`}>{c.confidence} confidence</span></div>
              <div className="meter"><span style={{ width: `${CONF[c.confidence]}%` }} /></div>
              <p>{c.reasoning}</p>
              {c.supporting_findings.length > 0 && <><b className="small">Supporting</b><ul className="tight small">{c.supporting_findings.map((x, j) => <li key={j}>{x}</li>)}</ul></>}
              {c.against_findings.length > 0 && <><b className="small">Against</b><ul className="tight small">{c.against_findings.map((x, j) => <li key={j}>{x}</li>)}</ul></>}
            </div>
          ))}
          {r.analysis.contributing_factors?.length > 0 && <p><b>Contributing factors:</b> {r.analysis.contributing_factors.join(', ')}</p>}
          <p className="alert warn small"><b>Uncertainty:</b> {r.analysis.uncertainty_note}</p>
        </div>
      )}

      {tab === 'labs' && (
        <div className="card">
          {r.labs.length === 0 ? <p className="muted">No lab report uploaded.</p> : (
            <>
              <div className="table-wrap"><table>
                <thead><tr><th>Test</th><th>Value</th><th>Reference</th><th>Status</th><th>What it means</th></tr></thead>
                <tbody>{r.labs.map((l, i) => (
                  <tr key={i}>
                    <td>{l.name}</td><td><b>{l.value}</b> {l.unit}</td>
                    <td className="small">{l.ref_low ?? ''} – {l.ref_high ?? ''}</td>
                    <td><span className={`badge ${flagClass(l.flag)}`}>{l.flag.replace('_', ' ')}</span></td>
                    <td className="small">{l.meaning}</td>
                  </tr>
                ))}</tbody>
              </table></div>
              <p className="small muted">Flags are calculated by comparing with the lab's printed range (or standard adult ranges). Always confirm with your doctor.</p>
            </>
          )}
        </div>
      )}

      {tab === 'meds' && med && (
        <div>
          <p className="alert warn"><b>For your doctor or pharmacist to review.</b> {med.disclaimer}</p>
          {med.items.length === 0 && <p className="card muted">No over-the-counter medicine is suggested. Please see a doctor.</p>}
          <div className="grid grid-2">
            {med.items.map(m => (
              <div className="card" key={m.id}>
                <div className="row spread"><h3>{m.name}</h3>{m.prescription_only && <span className="badge b-rx">Prescription only</span>}</div>
                <p className="small muted">Brands: {m.brands.join(', ')} · for {m.for_condition}</p>
                <p>{m.purpose}</p>
                <p className="small"><b>Dose:</b> {m.dose}<br /><b>How often:</b> {m.frequency}<br /><b>Take:</b> {FOOD[m.food]}</p>
                {m.interactions.map((x, i) => <p key={i} className="alert warn small">{x.severity} interaction with {x.with}: {x.note}</p>)}
                {m.warnings.length > 0 && <ul className="tight small">{m.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}
                <a className="small" href={m.source} target="_blank" rel="noreferrer">Source</a>
              </div>
            ))}
          </div>
          {(med.excluded.length > 0 || med.avoid.length > 0) && (
            <div className="card">
              <h3>Not suggested for you</h3>
              <ul className="tight">
                {med.excluded.map(m => <li key={m.id}><b>{m.name}</b>: {m.reasons.join('; ')}</li>)}
                {med.avoid.map((a, i) => <li key={i}><b>{a.name}</b>: {a.reason}</li>)}
              </ul>
            </div>
          )}
          {med.timetable.length > 0 && (
            <div className="card">
              <h3>Daily medicine timetable</h3>
              <div className="table-wrap"><table>
                <thead><tr><th>Time</th><th>Medicine</th><th>Dose</th><th>How</th></tr></thead>
                <tbody>{med.timetable.map((t, i) => (
                  <tr key={i}><td><b>{t.time}</b></td><td>{t.medicine}{t.source === 'your current medicine' && <span className="badge b-info" style={{ marginLeft: 6 }}>current</span>}</td><td className="small">{t.dose}</td><td className="small">{t.instruction}</td></tr>
                ))}</tbody>
              </table></div>
            </div>
          )}
        </div>
      )}

      {tab === 'diet' && r.diet && <DietChart diet={r.diet} />}

      {tab === 'prices' && <div className="card"><PriceCompare caseId={caseData.id} suggestions={priceSuggestions} initial={r.prices || {}} /></div>}

      {tab === 'report' && (
        <div className="card">
          <h3>Patient</h3>
          <p className="small">{r.patient.name}, {r.patient.age}, {r.patient.sex} · Conditions: {r.patient.conditions?.join(', ') || 'none'} · Allergies: {r.patient.allergies?.join(', ') || 'none'} · Medicines: {r.patient.medications?.join(', ') || 'none'}</p>
          <h3>Symptoms</h3>
          <p className="small">{r.symptoms.complaint} · {r.symptoms.duration} · severity {r.symptoms.severity}/10</p>
          {r.symptoms.key_symptoms?.length > 0 && <p className="small">Key symptoms: {r.symptoms.key_symptoms.join(', ')}</p>}
          <h3>Follow-up answers</h3>
          <ul className="tight small">{r.follow_up.map((q, i) => <li key={i}>{q.question} <b>{q.answer}</b></li>)}</ul>
          <h3>How the agents worked</h3>
          <ol className="small">{r.agents.map((a, i) => <li key={i}><b>{a.agent}</b>: {a.note}</li>)}</ol>
          <h3>References</h3>
          <ul className="tight small">{r.references.map(ref => <li key={ref.id}>{ref.title}: <a href={ref.source} target="_blank" rel="noreferrer">{ref.source}</a></li>)}</ul>
        </div>
      )}
    </div>
  )
}
