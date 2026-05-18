import type { ActiveCall, CallRecord, CallSummary, Lawyer, User } from './types'

async function api<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`)
  return res.json() as Promise<T>
}

export const listActiveCalls = () => api<ActiveCall[]>('/api/active-calls')
export const listCalls = (limit = 50) => api<CallSummary[]>(`/api/calls?limit=${limit}`)
export const getCall = (id: string) => api<CallRecord>(`/api/calls/${id}`)
export const listUsers = () => api<User[]>('/api/users')
export const listLawyers = () => api<Lawyer[]>('/api/lawyers')
