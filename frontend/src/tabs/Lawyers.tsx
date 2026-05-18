import { useEffect, useState } from 'react'
import { listLawyers } from '../api'
import { prettyPracticeAreas } from '../lib/format'
import type { Lawyer } from '../types'

const AVAILABILITY_CLASSES: Record<Lawyer['availability_status'], string> = {
  now: 'bg-brand-green text-brand-light',
  business_hours: 'bg-brand-blue text-brand-light',
  unavailable: 'bg-brand-mid text-brand-dark',
}

export function Lawyers() {
  const [lawyers, setLawyers] = useState<Lawyer[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listLawyers()
      .then(setLawyers)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="h-full overflow-auto">
      <div className="px-6 py-4 border-b border-brand-light-gray">
        <h2 className="font-heading text-lg font-semibold">Lawyers</h2>
        <div className="text-xs text-brand-mid">
          {loading ? 'Loading…' : `${lawyers.length} in network`}
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
              <th className="text-left px-6 py-2 font-heading font-medium">Name / Firm</th>
              <th className="text-left px-6 py-2 font-heading font-medium">Bar</th>
              <th className="text-left px-6 py-2 font-heading font-medium">Practice areas</th>
              <th className="text-left px-6 py-2 font-heading font-medium">Jurisdictions</th>
              <th className="text-left px-6 py-2 font-heading font-medium">Rate</th>
              <th className="text-left px-6 py-2 font-heading font-medium">Availability</th>
              <th className="text-left px-6 py-2 font-heading font-medium">Emergencies</th>
              <th className="text-left px-6 py-2 font-heading font-medium">Phone</th>
              <th className="text-left px-6 py-2 font-heading font-medium">ID</th>
            </tr>
          </thead>
          <tbody>
            {lawyers.map((lw) => (
              <tr key={lw.id} className="border-t border-brand-light-gray">
                <td className="px-6 py-3">
                  <div className="font-medium">{lw.name}</div>
                  <div className="text-xs text-brand-mid">{lw.firm}</div>
                </td>
                <td className="px-6 py-3 font-mono text-xs">{lw.bar_state}</td>
                <td className="px-6 py-3 text-xs">{prettyPracticeAreas(lw.practice_areas)}</td>
                <td className="px-6 py-3 text-xs">
                  {lw.jurisdictions
                    .map((j) =>
                      j.counties.length ? `${j.state} (${j.counties.join(', ')})` : j.state,
                    )
                    .join(' · ')}
                </td>
                <td className="px-6 py-3 font-mono text-xs">${lw.hourly_rate}/hr</td>
                <td className="px-6 py-3">
                  <span
                    className={`inline-block px-2 py-0.5 text-xs font-heading rounded-full ${AVAILABILITY_CLASSES[lw.availability_status]}`}
                  >
                    {lw.availability_status.replace('_', ' ')}
                  </span>
                </td>
                <td className="px-6 py-3">{lw.accepts_emergencies ? 'Yes' : 'No'}</td>
                <td className="px-6 py-3 font-mono text-xs">{lw.phone}</td>
                <td className="px-6 py-3 font-mono text-xs text-brand-mid">{lw.id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
