import { useState } from 'react'
import { api } from '../api'

const rs = v => `₹${Number(v).toFixed(2)}`

export default function PriceCompare({ caseId, suggestions = [], initial = {} }) {
  const [query, setQuery] = useState(suggestions[0] || '')
  const [results, setResults] = useState(initial)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  async function search(q, refresh = false) {
    if (!q || q.trim().length < 2) return
    setError(''); setBusy(q.trim())
    try {
      const data = await api(`/cases/${caseId}/prices`, { method: 'POST', body: { medicine: q.trim(), refresh } })
      setResults(r => ({ [q.trim()]: data, ...Object.fromEntries(Object.entries(r).filter(([k]) => k !== q.trim())) }))
    } catch (err) { setError(err.message) } finally { setBusy('') }
  }

  return (
    <div>
      <p className="muted">Checks live prices on PharmEasy, Netmeds, Tata 1mg and Apollo Pharmacy at the same time and compares the same medicine side by side.
        Buy prescription medicines only with a doctor's prescription.</p>
      <form className="row" onSubmit={e => { e.preventDefault(); search(query) }}>
        <input style={{ flex: 1, minWidth: 200 }} value={query} onChange={e => setQuery(e.target.value)} placeholder="Medicine or brand with strength, e.g. Dolo 650" />
        <button className="btn" disabled={!!busy}>{busy ? 'Checking 4 sites…' : 'Compare prices'}</button>
      </form>
      {suggestions.length > 0 && (
        <div className="row" style={{ marginTop: '.5rem' }}>
          <span className="small muted">Quick search:</span>
          {suggestions.map(s => <button key={s} className="choice" onClick={() => { setQuery(s); search(s) }}>{s}</button>)}
        </div>
      )}
      {busy && <div className="row" style={{ marginTop: '.8rem' }}><div className="spinner" /> Checking PharmEasy, Netmeds, 1mg and Apollo…</div>}
      {error && <p className="error">{error}</p>}
      {Object.entries(results).map(([q, d]) => <PriceResult key={q} q={q} d={d} busy={busy === q} onRefresh={() => search(q, true)} />)}
    </div>
  )
}

function PriceResult({ q, d, busy, onRefresh }) {
  const [showAll, setShowAll] = useState(false)
  const bySite = d.by_site || []
  const c = d.cheapest
  const perUnit = d.compare_basis === 'per_unit'

  return (
    <div className="card" style={{ marginTop: '1rem' }}>
      <div className="row spread">
        <div>
          <h3 style={{ marginBottom: 0 }}>{q}</h3>
          <span className="small muted">Price found on {d.sites_with_price ?? '-'} of {d.sites_checked ?? '-'} sites checked live · {new Date(d.checked_at).toLocaleString()}{d.cached ? ' (saved result)' : ''}</span>
        </div>
        <button className="btn ghost small" onClick={onRefresh} disabled={busy}>{busy ? 'Checking…' : 'Check again'}</button>
      </div>

      {c && (
        <div className="alert ok price-best" style={{ marginTop: '.8rem' }}>
          <b>Cheapest: {rs(c.price)} on {c.source}</b>
          {c.per_unit && <> ({rs(c.per_unit)} per {c.unit})</>} · {c.name}{c.pack && ` (${c.pack})`}
          {d.saving > 0 && <> · <b>save up to {rs(d.saving)}</b> compared with the costliest site</>}
          {c.url && <> · <a href={c.url} target="_blank" rel="noreferrer">Open</a></>}
        </div>
      )}

      <div className="table-wrap">
        <table>
          <thead><tr><th>Website</th><th>Product</th><th>Price</th><th>MRP</th><th>{perUnit ? `Per ${c?.unit || 'unit'}` : 'Pack'}</th><th>Compared</th><th></th></tr></thead>
          <tbody>
            {bySite.map(s => {
              const o = s.best
              const isBest = o && c && o.source === c.source && o.name === c.name
              return (
                <tr key={s.source} style={isBest ? { background: 'var(--ok-soft)' } : undefined}>
                  <td><b>{s.source}</b></td>
                  {o ? (
                    <>
                      <td className="small">{o.name}{o.pack && <div className="muted">{o.pack}</div>}</td>
                      <td><b>{rs(o.price)}</b>{o.discount_pct > 0 && <div className="small" style={{ color: 'var(--ok)' }}>{o.discount_pct}% off</div>}</td>
                      <td className="small muted">{o.mrp ? rs(o.mrp) : '-'}</td>
                      <td className="small">{perUnit ? (o.per_unit ? rs(o.per_unit) : '-') : (o.units ? `${o.units} ${o.unit}` : '-')}</td>
                      <td>
                        {isBest ? <span className="badge b-low">Cheapest</span>
                          : o.comparable === false ? <span className="badge b-unknown" title="Different form or pack, e.g. syrup vs tablets">Different form</span>
                          : o.vs_cheapest_pct != null ? <span className="badge b-moderate">+{o.vs_cheapest_pct}%</span> : '-'}
                      </td>
                      <td>{(o.url || s.url) && <a className="btn secondary small" href={o.url || s.url} target="_blank" rel="noreferrer">Open</a>}</td>
                    </>
                  ) : (
                    <>
                      <td colSpan={5} className="small muted">{s.live ? `Not found (${s.status})` : 'Price not shown automatically on this site'}</td>
                      <td><a className="btn ghost small" href={s.url} target="_blank" rel="noreferrer">Search</a></td>
                    </>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <p className="small" style={{ marginTop: '.6rem' }}>
        Cheaper generic: <a href={d.jan_aushadhi.url} target="_blank" rel="noreferrer">{d.jan_aushadhi.name}</a>
        {perUnit && <> · Compared by price per {c?.unit}, so different pack sizes are fair.</>}
      </p>

      {d.offers?.length > 0 && (
        <>
          <button className="btn ghost small" onClick={() => setShowAll(!showAll)}>{showAll ? 'Hide' : 'Show'} all {d.offers.length} results</button>
          {showAll && (
            <div className="table-wrap" style={{ marginTop: '.5rem' }}><table>
              <thead><tr><th>Website</th><th>Product</th><th>Price</th><th>Per unit</th><th></th></tr></thead>
              <tbody>{d.offers.map((o, i) => (
                <tr key={i}><td className="small">{o.source}</td><td className="small">{o.name} {o.pack && <span className="muted">({o.pack})</span>}</td>
                  <td><b>{rs(o.price)}</b></td><td className="small">{o.per_unit ? `${rs(o.per_unit)}/${o.unit}` : '-'}</td>
                  <td>{o.url && <a href={o.url} target="_blank" rel="noreferrer">View</a>}</td></tr>
              ))}</tbody>
            </table></div>
          )}
        </>
      )}
      <p className="small muted">{d.note}</p>
    </div>
  )
}
