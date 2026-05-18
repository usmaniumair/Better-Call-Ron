import { useEffect, useState } from 'react'
import { listUsers } from '../api'
import type { User } from '../types'

export function Users() {
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listUsers()
      .then(setUsers)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="h-full overflow-auto">
      <div className="px-6 py-4 border-b border-brand-light-gray">
        <h2 className="font-heading text-lg font-semibold">Users</h2>
        <div className="text-xs text-brand-mid">
          {loading ? 'Loading…' : `${users.length} registered`}
        </div>
      </div>

      {error && (
        <div className="mx-6 mt-4 p-3 rounded bg-brand-orange/10 text-brand-orange text-sm">
          {error}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-max">
          <thead className="bg-brand-light-gray/50 text-brand-mid uppercase text-xs">
            <tr>
              <th className="text-left px-6 py-2 font-heading font-medium">Name</th>
              <th className="text-left px-6 py-2 font-heading font-medium">Phones</th>
              <th className="text-left px-6 py-2 font-heading font-medium">Email</th>
              <th className="text-left px-6 py-2 font-heading font-medium">Home jurisdiction</th>
              <th className="text-left px-6 py-2 font-heading font-medium">Emergency contacts</th>
              <th className="text-left px-6 py-2 font-heading font-medium">ID</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-t border-brand-light-gray">
                <td className="px-6 py-3 font-medium">{u.name}</td>
                <td className="px-6 py-3 font-mono text-xs">{u.phone_numbers.join(', ')}</td>
                <td className="px-6 py-3 font-mono text-xs">{u.email || '—'}</td>
                <td className="px-6 py-3">
                  {u.home_jurisdiction.state}
                  {u.home_jurisdiction.county ? ` · ${u.home_jurisdiction.county}` : ''}
                </td>
                <td className="px-6 py-3 text-xs">
                  {u.emergency_contacts.length === 0
                    ? '—'
                    : u.emergency_contacts
                        .map((c) => `${c.name} (${c.relationship})`)
                        .join(', ')}
                </td>
                <td className="px-6 py-3 font-mono text-xs text-brand-mid">{u.id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
