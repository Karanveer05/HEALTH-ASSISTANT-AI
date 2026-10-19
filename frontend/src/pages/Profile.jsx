import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../App.jsx'

const EMPTY = {
  name: '', age: '', sex: 'male', weight_kg: '', height_cm: '', conditions: '', allergies: '', medications: '',
  pregnant: false, smoker: false, alcohol: false, diet_preference: 'veg', region: 'any',
  wake_time: '07:00', breakfast_time: '08:30', lunch_time: '13:30', snack_time: '17:30', dinner_time: '20:30', sleep_time: '22:30',
  emergency_contact_name: '', emergency_contact_phone: '', notes: '',
}
const LISTS = ['conditions', 'allergies', 'medications']

export default function Profile() {
  const [f, setF] = useState(EMPTY)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const { user, setUser } = useAuth()
  const navigate = useNavigate()

  useEffect(() => {
    api('/profile').then(p => {
      if (!p) return
      const v = { ...EMPTY, ...p }
      LISTS.forEach(k => { v[k] = (p[k] || []).join(', ') })
      ;['weight_kg', 'height_cm'].forEach(k => { v[k] = p[k] ?? '' })
      setF(v)
    }).catch(e => setError(e.message))
  }, [])

  const set = k => e => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })

  async function save(e) {
    e.preventDefault()
    setError(''); setSaved(false)
    const body = { ...f, age: Number(f.age) }
    LISTS.forEach(k => { body[k] = f[k].split(',').map(s => s.trim()).filter(Boolean) })
    ;['weight_kg', 'height_cm'].forEach(k => { body[k] = f[k] === '' ? null : Number(f[k]) })
    if (body.sex !== 'female') body.pregnant = false
    try {
      await api('/profile', { method: 'PUT', body })
      const first = !user.has_profile
      setUser({ ...user, has_profile: true })
      setSaved(true)
      if (first) navigate('/new')
    } catch (err) { setError(err.message) }
  }

  return (
    <main className="container narrow">
      <h1>Your health profile</h1>
      <p className="muted">This information is encrypted and used only for your own analysis. It helps avoid unsafe medicines and foods.</p>
      <form onSubmit={save}>
        <div className="card">
          <h2>Basic details</h2>
          <div className="grid grid-2">
            <div><label htmlFor="name">Full name</label><input id="name" value={f.name} onChange={set('name')} required /></div>
            <div><label htmlFor="age">Age</label><input id="age" type="number" min="0" max="120" value={f.age} onChange={set('age')} required /></div>
            <div><label htmlFor="sex">Sex</label>
              <select id="sex" value={f.sex} onChange={set('sex')}><option value="male">Male</option><option value="female">Female</option><option value="other">Other</option></select></div>
            <div className="grid grid-2" style={{ gap: '.5rem' }}>
              <div><label htmlFor="wt">Weight (kg)</label><input id="wt" type="number" step="0.1" value={f.weight_kg} onChange={set('weight_kg')} /></div>
              <div><label htmlFor="ht">Height (cm)</label><input id="ht" type="number" value={f.height_cm} onChange={set('height_cm')} /></div>
            </div>
          </div>
          {f.sex === 'female' && <label className="check"><input type="checkbox" checked={f.pregnant} onChange={set('pregnant')} /> I am pregnant</label>}
          <label className="check"><input type="checkbox" checked={f.smoker} onChange={set('smoker')} /> I smoke</label>
          <label className="check"><input type="checkbox" checked={f.alcohol} onChange={set('alcohol')} /> I drink alcohol regularly</label>
        </div>

        <div className="card">
          <h2>Medical history</h2>
          <label htmlFor="cond">Existing conditions</label>
          <input id="cond" value={f.conditions} onChange={set('conditions')} placeholder="e.g. diabetes, high BP, asthma" />
          <label htmlFor="all">Allergies (medicines and foods)</label>
          <input id="all" value={f.allergies} onChange={set('allergies')} placeholder="e.g. penicillin, ibuprofen, peanuts, milk" />
          <label htmlFor="meds">Medicines you take now</label>
          <input id="meds" value={f.medications} onChange={set('medications')} placeholder="e.g. Thyronorm 50, Metformin 500" />
          <p className="hint">Separate items with commas.</p>
        </div>

        <div className="card">
          <h2>Food and daily routine</h2>
          <p className="muted small">Used to build your diet chart and medicine timetable.</p>
          <div className="grid grid-2">
            <div><label htmlFor="diet">Diet</label>
              <select id="diet" value={f.diet_preference} onChange={set('diet_preference')}>
                <option value="veg">Vegetarian</option><option value="egg">Eggetarian</option><option value="nonveg">Non-vegetarian</option></select></div>
            <div><label htmlFor="region">Food style</label>
              <select id="region" value={f.region} onChange={set('region')}>
                <option value="any">Any</option><option value="north">North Indian</option><option value="south">South Indian</option></select></div>
          </div>
          <div className="grid grid-3">
            {[['wake_time', 'Wake up'], ['breakfast_time', 'Breakfast'], ['lunch_time', 'Lunch'], ['snack_time', 'Evening snack'], ['dinner_time', 'Dinner'], ['sleep_time', 'Sleep']].map(([k, l]) => (
              <div key={k}><label htmlFor={k}>{l}</label><input id={k} type="time" value={f[k]} onChange={set(k)} required /></div>
            ))}
          </div>
        </div>

        <div className="card">
          <h2>Emergency contact</h2>
          <div className="grid grid-2">
            <div><label htmlFor="ecn">Name</label><input id="ecn" value={f.emergency_contact_name} onChange={set('emergency_contact_name')} /></div>
            <div><label htmlFor="ecp">Phone</label><input id="ecp" type="tel" value={f.emergency_contact_phone} onChange={set('emergency_contact_phone')} /></div>
          </div>
        </div>
        {error && <p className="error">{error}</p>}
        {saved && <p className="alert ok">Profile saved.</p>}
        <button className="btn big">Save profile</button>
      </form>
    </main>
  )
}
