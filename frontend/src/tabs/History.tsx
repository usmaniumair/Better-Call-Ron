import { Fragment, useEffect, useState } from 'react'
import { getCall, listCalls } from '../api'
import type { CallRecord, CallSummary, UrgencyFilter } from '../types'
import { StatusBadge, UrgencyBadge } from '../components/Badge'
import { FilterChips } from '../components/FilterChips'

function formatDateTime(ts: string | null): string {
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleString([], {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ts
  }
}

export function History() {
  const [calls, setCalls] = useState<CallSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [urgencyFilter, setUrgencyFilter] = useState<UrgencyFilter>('all')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [expandedRecord, setExpandedRecord] = useState<CallRecord | null>(null)
  const [expandedLoading, setExpandedLoading] = useState(false)

  const reload = async () => {
    setLoading(true)
    setError(null)
    try {
      setCalls(await listCalls(50))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    reload()
  }, [])

  useEffect(() => {
    if (!expandedId) {
      setExpandedRecord(null)
      return
    }
    let cancelled = false
    setExpandedLoading(true)
    setExpandedRecord(null)
    getCall(expandedId)
      .then((r) => {
        if (!cancelled) setExpandedRecord(r)
      })
      .catch(() => {
        if (!cancelled) setExpandedRecord(null)
      })
      .finally(() => {
        if (!cancelled) setExpandedLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [expandedId])

  const filteredCalls = urgencyFilter === 'all'
    ? calls
    : calls.filter((c) => c.urgency === urgencyFilter)

  return (
    <div className="h-full overflow-auto">
      <div className="px-6 py-4 border-b border-brand-light-gray flex items-center justify-between">
        <div>
          <h2 className="font-heading text-lg font-semibold">History</h2>
          <div className="text-xs text-brand-mid">
            {loading ? 'Loading…' : `${filteredCalls.length} of ${calls.length} calls`}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <FilterChips value={urgencyFilter} onChange={setUrgencyFilter} />
          <button
            onClick={reload}
            className="px-3 py-1 text-sm font-heading rounded-full border border-brand-mid hover:bg-brand-light-gray"
          >
            Reload
          </button>
        </div>
      </div>

      {error && (
        <div className="mx-6 mt-4 p-3 rounded bg-brand-orange/10 text-brand-orange text-sm">
          {error}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm table-fixed">
          <thead className="bg-brand-light-gray/50 text-brand-mid uppercase text-xs">
            <tr>
              <th className="text-left px-6 py-2 font-heading font-medium w-40">When</th>
              <th className="text-left px-6 py-2 font-heading font-medium w-40">From</th>
              <th className="text-left px-6 py-2 font-heading font-medium w-28">Urgency</th>
              <th className="text-left px-6 py-2 font-heading font-medium w-32">Status</th>
              <th className="text-left px-6 py-2 font-heading font-medium w-20">Turns</th>
              <th className="text-left px-6 py-2 font-heading font-medium">Call ID</th>
            </tr>
          </thead>
          <tbody>
          {filteredCalls.map((c) => {
            const expanded = c.call_id === expandedId
            return (
              <Fragment key={c.call_id}>
                <tr
                  onClick={() => setExpandedId(expanded ? null : c.call_id)}
                  className={`border-t border-brand-light-gray cursor-pointer hover:bg-brand-light-gray/30 ${
                    expanded ? 'bg-brand-light-gray/50' : ''
                  }`}
                >
                  <td className="px-6 py-3">{formatDateTime(c.started_at)}</td>
                  <td className="px-6 py-3 font-mono text-xs">{c.from_number || '—'}</td>
                  <td className="px-6 py-3"><UrgencyBadge value={c.urgency} /></td>
                  <td className="px-6 py-3"><StatusBadge value={c.status} /></td>
                  <td className="px-6 py-3">{c.turn_count}</td>
                  <td className="px-6 py-3 font-mono text-xs text-brand-mid">{c.call_id}</td>
                </tr>
                {expanded && (
                  <tr className="bg-brand-light-gray/30">
                    <td colSpan={6} className="px-6 py-4">
                      {expandedLoading && <div className="text-sm text-brand-mid italic">Loading call detail…</div>}
                      {expandedRecord && <CallDetail record={expandedRecord} />}
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
            {!loading && filteredCalls.length === 0 && (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-brand-mid">
                  No calls match this filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function CallDetail({ record }: { record: CallRecord }) {
  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between border-b border-brand-light-gray pb-2">
        <div>
          <div className="font-heading text-sm font-semibold">Call detail</div>
          <div className="text-xs text-brand-mid">
            {record.from_number || 'unknown caller'} · {formatDateTime(record.started_at)}
          </div>
        </div>
        <div className="font-mono text-xs text-brand-mid">{record.call_id}</div>
      </div>
      <div className="grid grid-cols-2 gap-6">
      <section>
        <h3 className="font-heading text-sm font-semibold uppercase tracking-wide text-brand-mid mb-3">
          Transcript ({record.turns.length} turns)
        </h3>
        <div className="space-y-2 max-h-96 overflow-auto pr-2">
          {record.turns.map((t, i) => {
            const isCaller = t.speaker === 'caller'
            return (
              <div key={i} className={`flex ${isCaller ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[85%] rounded-xl px-3 py-1.5 text-sm ${
                    isCaller
                      ? 'bg-brand-blue text-brand-light rounded-br-sm'
                      : 'bg-brand-light text-brand-dark border border-brand-light-gray rounded-bl-sm'
                  }`}
                >
                  <div className="text-[10px] opacity-70">{isCaller ? 'Caller' : 'Ron'}</div>
                  {t.text}
                </div>
              </div>
            )
          })}
        </div>
      </section>
      <section>
        <h3 className="font-heading text-sm font-semibold uppercase tracking-wide text-brand-mid mb-3">
          Tool calls ({record.tool_log.length})
        </h3>
        <div className="space-y-3 max-h-96 overflow-auto pr-2">
          {record.tool_log.map((t, i) => {
            const errored = 'error' in t.result
            return (
              <div
                key={i}
                className={`rounded border p-3 text-xs ${
                  errored
                    ? 'border-brand-orange/40 bg-brand-orange/5'
                    : 'border-brand-light-gray bg-brand-light'
                }`}
              >
                <div className="font-mono font-semibold text-brand-dark">{t.name}</div>
                <details className="mt-1">
                  <summary className="cursor-pointer text-brand-mid">input</summary>
                  <pre className="mt-1 whitespace-pre-wrap break-words font-mono text-[11px] text-brand-dark">
                    {JSON.stringify(t.input, null, 2)}
                  </pre>
                </details>
                <details className="mt-1">
                  <summary className="cursor-pointer text-brand-mid">result</summary>
                  <pre className="mt-1 whitespace-pre-wrap break-words font-mono text-[11px] text-brand-dark">
                    {JSON.stringify(t.result, null, 2)}
                  </pre>
                </details>
              </div>
            )
          })}
          {record.tool_log.length === 0 && (
            <div className="text-sm text-brand-mid">No tool calls.</div>
          )}
        </div>
      </section>
      </div>
    </div>
  )
}
