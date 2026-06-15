import { createContext, useContext, useState, useEffect } from 'react'

const SESSION_KEY = 'mra_auth_session'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(() => {
    try {
      const stored = sessionStorage.getItem(SESSION_KEY)
      return stored ? JSON.parse(stored) : { isAuthenticated: false, username: '' }
    } catch {
      return { isAuthenticated: false, username: '' }
    }
  })

  function login(username, password) {
    const validUser = import.meta.env.VITE_AUTH_USER || 'admin'
    const validPass = import.meta.env.VITE_AUTH_PASS || 'demo1234'
    if (username === validUser && password === validPass) {
      const session = { isAuthenticated: true, username }
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(session))
      setAuth(session)
      return true
    }
    return false
  }

  function logout() {
    sessionStorage.removeItem(SESSION_KEY)
    setAuth({ isAuthenticated: false, username: '' })
  }

  return (
    <AuthContext.Provider value={{ ...auth, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
