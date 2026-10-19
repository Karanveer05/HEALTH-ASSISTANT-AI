import { useState } from 'react'

export default function DietChart({ diet }) {
  const [mode, setMode] = useState('with_medicines')
  const [day, setDay] = useState(0)
  const chart = diet[mode] || diet.with_medicines

  return (
    <div>
      <div className="row spread">
        <div className="toggle" role="tablist">
          <button className={mode === 'with_medicines' ? 'on' : ''} onClick={() => setMode('with_medicines')}>With medicines</button>
          <button className={mode === 'natural' ? 'on' : ''} disabled={!diet.natural_allowed} onClick={() => setMode('natural')}
            title={diet.natural_allowed ? '' : diet.natural_reason}>Natural (no medicine)</button>
        </div>
        <button className="btn ghost small no-print" onClick={() => window.print()}>Print</button>
      </div>
      <p className={`alert ${diet.natural_allowed ? 'info' : 'warn'} small`}>{diet.natural_reason}</p>
      {chart.keep_taking && <p className="alert warn small">{chart.keep_taking}</p>}

      <div className="daypick">
        {chart.days.map((d, i) => <button key={d.day} className={`choice ${i === day ? 'on' : ''}`} onClick={() => setDay(i)}>{d.day}</button>)}
      </div>
      <div className="card">
        <div className="row spread"><h3>{chart.days[day].day}</h3><span className="small muted">about {chart.days[day].kcal} kcal from listed foods</span></div>
        {chart.days[day].slots.map(s => (
          <div className="slot" key={s.slot}>
            <div className="slot-time">{s.time}<small>{s.label}</small></div>
            <div>
              {s.items.map((it, i) => (
                <div key={i} className={`item ${it.kind}`}>
                  {it.kind === 'medicine' && '💊 '}{it.kind === 'remedy' && '🌿 '}{it.text}
                  {it.kind === 'medicine' && <span className="note"> at {it.time}, {it.note}</span>}
                  {it.kind === 'remedy' && <div className="note">{it.note}</div>}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {chart.through_day?.length > 0 && (
        <div className="card"><h3>Through the day</h3><ul className="tight">{chart.through_day.map((t, i) => <li key={i}>{t}</li>)}</ul></div>
      )}
      <div className="grid grid-2">
        <div className="card">
          <h3>Diet focus</h3>
          <p className="small"><b>Include:</b> {chart.focus_tags.map(t => t.replace(/_/g, ' ')).join(', ') || '-'}</p>
          <p className="small"><b>Avoid:</b> {chart.avoid_tags.map(t => t.replace(/_/g, ' ')).join(', ') || '-'}</p>
          <ul className="tight small">{chart.tips.map((t, i) => <li key={i}>{t}</li>)}</ul>
        </div>
        <div className="card">
          <h3>Lifestyle</h3>
          <ul className="tight small">{chart.lifestyle.map((t, i) => <li key={i}>{t}</li>)}</ul>
        </div>
      </div>
    </div>
  )
}
