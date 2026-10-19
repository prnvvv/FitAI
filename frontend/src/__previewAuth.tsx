/** Stub auth for the throwaway chat verification harness. Never committed. */
import { createContext, useContext } from 'react'

interface StubUser {
  displayName: string
}

const StubAuthContext = createContext<{ user: StubUser | null }>({ user: null })

export function AuthProvider({ children }: { children: React.ReactNode }) {
  return <StubAuthContext.Provider value={{ user: { displayName: 'Tester' } }}>{children}</StubAuthContext.Provider>
}

export function useAuth() {
  return useContext(StubAuthContext)
}