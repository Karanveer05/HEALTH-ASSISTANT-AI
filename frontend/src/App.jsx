import { createContext, useContext, useEffect, useState } from 'react'
import { Navigate, NavLink, Route, Routes, useNavigate } from 'react-router-dom'
import { api, getToken, setToken } from './api'
import Login from './pages/Login.jsx'
import Profile from './pages/Profile.jsx'
import Dashboard from './pages/Dashboard.jsx'
import NewCase from './pages/NewCase.jsx'
import CaseFlow from './pages/CaseFlow.jsx'
import EmergencyPage from './pages/EmergencyPage.jsx'
import Privacy from './pages/Privacy.jsx'

const AuthCtx = createContext(null)
export const useAuth = () => useContext(AuthCtx)

function Protected({ children, needProfile = true }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  if (needProfile && !user.has_profile) return <Navigate to="/profile" replace />
  return children
}

export default function App() {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    if (!getToken()) { setReady(true); return }
    api('/auth/me').then(setUser).catch(() => setToken(null)).finally(() => setReady(true))
  }, [])

  const logout = () => { setToken(null); setUser(null); navigate('/login') }

  if (!ready) return <div className="container"><div className="spinner" /></div>

  return (
    <AuthCtx.Provider value={{ user, setUser, logout }}>
      <header className="topbar">
        <div className="topbar-inner">
          <NavLink to="/" className="logo"><span className="logo-mark">+</span> HealthAssist AI</NavLink>
          <nav className="nav">
            {user && <>
              <NavLink to="/" end>Home</NavLink>
              <NavLink to="/new">New check</NavLink>
              <NavLink to="/profile">Profile</NavLink>
              <NavLink to="/privacy">Privacy</NavLink>
              <button onClick={logout}>Log out</button>
            </>}
            <NavLink to="/emergency" className="sos">Emergency</NavLink>
          </nav>
        </div>
      </header>
      <Routes>
        <Route path="/login" element={user ? <Navigate to="/" /> : <Login />} />
        <Route path="/emergency" element={<EmergencyPage />} />
        <Route path="/profile" element={<Protected needProfile={false}><Profile /></Protected>} />
        <Route path="/privacy" element={<Protected needProfile={false}><Privacy /></Protected>} />
        <Route path="/new" element={<Protected><NewCase /></Protected>} />
        <Route path="/cases/:id" element={<Protected><CaseFlow /></Protected>} />
        <Route path="/" element={<Protected><Dashboard /></Protected>} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
      <p className="footer-note">
        HealthAssist AI gives decision-support information only. It does not diagnose or prescribe.
        Always consult a qualified doctor. In an emergency call <a href="tel:112">112</a> or <a href="tel:108">108</a>.
      </p>
    </AuthCtx.Provider>
  )
}
