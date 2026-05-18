import { useState } from 'react'
import type { TabKey } from './types'
import { LiveTranscripts } from './tabs/LiveTranscripts'
import { History } from './tabs/History'
import { Users } from './tabs/Users'
import { Lawyers } from './tabs/Lawyers'

const TABS: { key: TabKey; label: string }[] = [
  { key: 'live', label: 'Live Transcripts' },
  { key: 'history', label: 'History' },
  { key: 'users', label: 'Users' },
  { key: 'lawyers', label: 'Lawyers' },
]

export default function App() {
  const [tab, setTab] = useState<TabKey>('live')

  return (
    <div className="flex h-screen w-screen bg-brand-light text-brand-dark">
      <aside className="w-56 shrink-0 border-r border-brand-light-gray bg-brand-light flex flex-col">
        <div className="px-5 py-6">
          <div className="font-heading text-xl font-semibold leading-tight">
            Better Call Ron
          </div>
          <div className="text-sm text-brand-mid mt-1">Operator Panel</div>
        </div>
        <nav className="flex flex-col gap-1 px-3">
          {TABS.map((t) => {
            const selected = tab === t.key
            return (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`px-3 py-2 rounded font-heading text-left text-sm transition-colors ${
                  selected
                    ? 'bg-brand-dark text-brand-light'
                    : 'text-brand-dark hover:bg-brand-light-gray'
                }`}
              >
                {t.label}
              </button>
            )
          })}
        </nav>
      </aside>

      <main className="flex-1 min-w-0 overflow-hidden">
        {tab === 'live' && <LiveTranscripts />}
        {tab === 'history' && <History />}
        {tab === 'users' && <Users />}
        {tab === 'lawyers' && <Lawyers />}
      </main>
    </div>
  )
}
