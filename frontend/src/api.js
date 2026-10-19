// Small fetch wrapper. The login token lives in sessionStorage so it is cleared when the browser closes.
const TOKEN_KEY = 'hc_token'

export function getToken() {
  try { return sessionStorage.getItem(TOKEN_KEY) } catch { return null }
}

export function setToken(token) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token)
    else sessionStorage.removeItem(TOKEN_KEY)
  } catch { /* storage blocked */ }
}

export async function api(path, { method = 'GET', body, form, raw } = {}) {
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let payload
  if (form) payload = form
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  const res = await fetch(`/api${path}`, { method, headers, body: payload })
  if (res.status === 401 && token) {
    setToken(null)
    window.location.href = '/login'
    throw new Error('Session expired, please log in again')
  }
  if (!res.ok) {
    let msg = res.statusText
    try {
      const j = await res.json()
      msg = typeof j.detail === 'string' ? j.detail : (j.detail || []).map(d => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join(', ') || msg
    } catch { /* not JSON */ }
    throw new Error(msg)
  }
  return raw ? res : res.json()
}

export async function downloadPdf(caseId) {
  const res = await api(`/cases/${caseId}/report.pdf`, { raw: true })
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `health-report-${caseId}.pdf`
  a.click()
  URL.revokeObjectURL(url)
}
