import { useEffect, useRef, useState } from 'react'
import { useLocation, useParams } from 'react-router-dom'
import { api } from '../api'
import EmergencyOverlay from '../components/EmergencyOverlay.jsx'
import ResultView, { flagClass } from '../components/ResultView.jsx'

const AGENTS = ['Symptom Analysis Agent', 'Medical Report Agent', 'Medical Knowledge Agent (RAG)', 'Orchestrator', 'Risk Assessment Agent', 'Medication Agent', 'Diet Agent']

function Steps({ c }) {
  const qDone = c.plan?.enough_info
  const order = ['Symptoms', 'Follow-up questions', 'Lab report', 'Analysis']
  const idx = c.status === 'analyzed' ? 4 : c.status === 'questions' ? 1 : 2
  return (
    <div className="steps">
      {order.map((s, i) => <div key={s} className={`step ${i < idx || (i === 1 && qDone) ? 'done' : i === idx ? 'now' : ''}`}>{i + 1}. {s}</div>)}
    </div>
  )
}

function Question({ q, value, onChange }) {
  const opts = q.type === 'yes_no' ? ['Yes', 'No', 'Not sure'] : q.type === 'choice' ? q.options : null
  return (
    <div className="question">
      <b>{q.question}</b>
      {q.why && <div className="why">{q.why}</div>}
      {opts ? (
        <div className="row" style={{ marginTop: '.4rem' }}>
          {opts.map(o => <button type="button" key={o} className={`choice ${value === o ? 'on' : ''}`} onClick={() => onChange(o)}>{o}</button>)}
        </div>
      ) : (
        <input style={{ marginTop: '.4rem' }} type={q.type === 'number' ? 'number' : 'text'} value={value || ''} onChange={e => onChange(e.target.value)} placeholder="Your answer" />
      )}
    </div>
  )
}

export default function CaseFlow() {
  const { id } = useParams()
  const location = useLocation()
  const [c, setC] = useState(null)
  const [answers, setAnswers] = useState({})
  const [emergency, setEmergency] = useState(location.state?.emergency || null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [upload, setUpload] = useState(null)
  const fileRef = useRef()

  useEffect(() => {
    api(`/cases/${id}`).then(setC).catch(e => setError(e.message))
  }, [id])

  function apply(next) {
    setC(next)
    if (next.new_emergency) setEmergency(next.new_emergency)
  }

  async function sendAnswers(e) {
    e.preventDefault()
    const list = c.plan.questions.map(q => ({ question: q.question, answer: (answers[q.question] || '').trim() || 'Not answered' }))
    setBusy('answers'); setError('')
    try { apply(await api(`/cases/${id}/answers`, { method: 'POST', body: { answers: list } })); setAnswers({}) }
    catch (err) { setError(err.message) } finally { setBusy('') }
  }

  async function uploadFile(file) {
    if (!file) return
    const form = new FormData()
    form.append('file', file)
    setBusy('upload'); setError(''); setUpload(null)
    try {
      const next = await api(`/cases/${id}/reports`, { method: 'POST', form })
      apply(next)
      setUpload(next.upload)
    } catch (err) { setError(err.message) } finally { setBusy(''); if (fileRef.current) fileRef.current.value = '' }
  }

  async function analyze() {
    setBusy('analyze'); setError('')
    try { apply(await api(`/cases/${id}/analyze`, { method: 'POST' })) }
    catch (err) { setError(err.message) } finally { setBusy('') }
  }

  if (error && !c) return <main className="container"><p className="error">{error}</p></main>
  if (!c) return <main className="container"><div className="spinner" /></main>

  const plan = c.plan || {}
  const asking = c.status === 'questions' && plan.questions?.length > 0

  return (
    <main className="container">
      <EmergencyOverlay emergency={emergency} onClose={() => setEmergency(null)} />
      <div className="row spread">
        <h1>Health check #{c.id}</h1>
        {c.emergency && <button className="btn danger small" onClick={() => setEmergency(c.emergency)}>Show emergency steps</button>}
      </div>
      <Steps c={c} />

      {c.status !== 'analyzed' && (
        <div className="grid grid-2">
          <div className="card">
            <h2>Your answers</h2>
            <div className="qa">
              <div className="bubble a"><b>{c.complaint}</b>{c.duration && ` · ${c.duration}`} · severity {c.severity}/10{c.other_symptoms && <><br />{c.other_symptoms}</>}</div>
              {c.qa.map((qa, i) => (
                <div key={i} style={{ display: 'contents' }}>
                  <div className="bubble q">{qa.question}</div>
                  <div className="bubble a">{qa.answer}</div>
                </div>
              ))}
            </div>
          </div>

          <div>
            {asking && (
              <form className="card" onSubmit={sendAnswers}>
                <h2>A few more questions</h2>
                <p className="small muted">These help narrow down the cause. Answer what you can.</p>
                {plan.questions.map(q => <Question key={q.question} q={q} value={answers[q.question]} onChange={v => setAnswers({ ...answers, [q.question]: v })} />)}
                <div className="row" style={{ marginTop: '.8rem' }}>
                  <button className="btn" disabled={!!busy}>{busy === 'answers' ? 'Thinking…' : 'Next'}</button>
                  <button type="button" className="btn ghost" disabled={!!busy} onClick={analyze}>Skip and analyse now</button>
                </div>
              </form>
            )}

            {!asking && (
              <div className="card">
                <h2>Lab report</h2>
                {plan.need_report && c.labs.length === 0 ? (
                  <div className="alert warn">
                    <b>A lab report would help.</b> Suggested tests:
                    <ul className="tight">{plan.suggested_tests.map(t => <li key={t}>{t}</li>)}</ul>
                    If you have a recent report, upload it. You can also continue without it.
                  </div>
                ) : <p className="muted">Optional: upload any recent lab report (PDF or photo) for a better analysis.</p>}
                <input ref={fileRef} type="file" accept="application/pdf,image/png,image/jpeg,image/webp" onChange={e => uploadFile(e.target.files[0])} disabled={!!busy} />
                {busy === 'upload' && <div className="row" style={{ marginTop: '.6rem' }}><div className="spinner" /> Reading the report (OCR)…</div>}
                {upload && <p className="alert ok small">Read with {upload.method}: found {upload.found} lab values.</p>}
                {c.labs.length > 0 && (
                  <div className="table-wrap" style={{ marginTop: '.6rem' }}><table>
                    <thead><tr><th>Test</th><th>Value</th><th>Status</th></tr></thead>
                    <tbody>{c.labs.map((l, i) => <tr key={i}><td>{l.name}</td><td>{l.value} {l.unit}</td><td><span className={`badge ${flagClass(l.flag)}`}>{l.flag.replace('_', ' ')}</span></td></tr>)}</tbody>
                  </table></div>
                )}
                <div className="row" style={{ marginTop: '1rem' }}>
                  <button className="btn big" onClick={analyze} disabled={!!busy}>{busy === 'analyze' ? 'Analysing…' : plan.need_report && c.labs.length === 0 ? 'Continue without report' : 'Analyse now'}</button>
                </div>
              </div>
            )}
            {busy === 'analyze' && (
              <div className="card">
                <div className="row"><div className="spinner" /><b>AI agents are working on your case…</b></div>
                <ol className="small muted">{AGENTS.map(a => <li key={a}>{a}</li>)}</ol>
              </div>
            )}
            {error && <p className="error">{error}</p>}
          </div>
        </div>
      )}

      {c.status === 'analyzed' && c.result && <ResultView caseData={c} onRerun={analyze} busy={busy === 'analyze'} />}
      {c.status === 'analyzed' && error && <p className="error">{error}</p>}
    </main>
  )
}
