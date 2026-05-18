import { useEffect, useRef, useState } from 'react'
import { listActiveCalls } from '../api'
import type { ActiveCall, Turn, UrgencyFilter } from '../types'
import { UrgencyBadge } from '../components/Badge'
import { FilterChips } from '../components/FilterChips'

type WsStatus = 'idle' | 'connecting' | 'live' | 'closed'

function wsUrl(callId: string): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}/transcript/${callId}`
}

function formatTime(ts: string | null): string {
  if (!ts) return ''
  try {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return ts
  }
}

export function LiveTranscripts() {
  const [activeCalls, setActiveCalls] = useState<ActiveCall[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [autoFollow, setAutoFollow] = useState(true)
  const [urgencyFilter, setUrgencyFilter] = useState<UrgencyFilter>('all')
  const [turns, setTurns] = useState<Turn[]>([])
  const [wsStatus, setWsStatus] = useState<WsStatus>('idle')
  const wsRef = useRef<WebSocket | null>(null)
  const transcriptEndRef = useRef<HTMLDivElement | null>(null)

  // Poll /api/active-calls every 2s.
  useEffect(() => {
    let cancelled = false
    const tick = async () => {
      try {
        const calls = await listActiveCalls()
        if (!cancelled) setActiveCalls(calls)
      } catch {
        /* ignore — likely backend restart */
      }
    }
    tick()
    const id = window.setInterval(tick, 2000)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [])

  // Auto-follow newest call.
  useEffect(() => {
    if (!autoFollow || activeCalls.length === 0) return
    const newest = activeCalls[0].call_id
    if (newest !== selectedId) setSelectedId(newest)
  }, [activeCalls, autoFollow, selectedId])

  // Open WebSocket on selectedId change.
  useEffect(() => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setTurns([])
    if (!selectedId) {
      setWsStatus('idle')
      return
    }
    setWsStatus('connecting')
    const ws = new WebSocket(wsUrl(selectedId))
    wsRef.current = ws
    ws.onopen = () => setWsStatus('live')
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data) as Turn & { callId: string }
        setTurns((prev) => [...prev, { speaker: msg.speaker, text: msg.text, ts: msg.ts }])
      } catch {
        /* ignore malformed */
      }
    }
    ws.onclose = () => setWsStatus('closed')
    ws.onerror = () => setWsStatus('closed')
    return () => {
      ws.close()
    }
  }, [selectedId])

  // Auto-scroll to bottom on new turn.
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [turns])

  const filteredCalls = urgencyFilter === 'all'
    ? activeCalls
    : activeCalls.filter((c) => c.urgency === urgencyFilter)

  return (
    <div className="flex h-full">
      {/* Left rail */}
      <div className="w-56 shrink-0 border-r border-brand-light-gray flex flex-col">
        <div className="p-4 border-b border-brand-light-gray space-y-3">
          <div className="font-heading font-semibold text-sm uppercase tracking-wide text-brand-mid">
            Active calls ({filteredCalls.length})
          </div>
          <FilterChips value={urgencyFilter} onChange={setUrgencyFilter} />
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={autoFollow}
              onChange={(e) => setAutoFollow(e.target.checked)}
              className="accent-brand-orange"
            />
            <span>Auto-follow newest</span>
          </label>
        </div>
        <div className="flex-1 overflow-auto">
          {filteredCalls.length === 0 ? (
            <div className="p-4 text-sm text-brand-mid">No active calls.</div>
          ) : (
            filteredCalls.map((call) => {
              const selected = call.call_id === selectedId
              return (
                <button
                  key={call.call_id}
                  onClick={() => {
                    setAutoFollow(false)
                    setSelectedId(call.call_id)
                  }}
                  className={`w-full text-left px-4 py-3 border-b border-brand-light-gray transition-colors ${
                    selected ? 'bg-brand-light-gray' : 'hover:bg-brand-light-gray/50'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="live-dot inline-block w-2 h-2 rounded-full bg-brand-orange" />
                    <UrgencyBadge value={call.urgency} />
                  </div>
                  <div className="font-mono text-xs text-brand-mid truncate">{call.call_id}</div>
                  <div className="text-xs text-brand-mid mt-1">{call.turn_count} turns · {formatTime(call.started_at)}</div>
                </button>
              )
            })
          )}
        </div>
      </div>

      {/* Right pane */}
      <div className="flex-1 min-w-0 flex flex-col">
        <div className="px-6 py-4 border-b border-brand-light-gray flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h2 className="font-heading text-lg font-semibold truncate">
              {selectedId ? 'Transcript' : 'No call selected'}
            </h2>
            {selectedId && (
              <div className="font-mono text-xs text-brand-mid truncate">{selectedId}</div>
            )}
          </div>
          <div className="shrink-0 flex items-center gap-2 text-xs uppercase tracking-wide text-brand-mid">
            <span
              className={`inline-block w-2 h-2 rounded-full ${
                wsStatus === 'live'
                  ? 'bg-brand-green'
                  : wsStatus === 'connecting'
                    ? 'bg-brand-orange'
                    : 'bg-brand-mid'
              }`}
              aria-hidden
            />
            <span>ws: {wsStatus}</span>
          </div>
        </div>
        <div className="flex-1 overflow-auto px-6 py-4 space-y-3">
          {turns.length === 0 ? (
            <div className="text-sm text-brand-mid">
              {selectedId ? 'Waiting for next turn…' : 'Pick a call on the left, or wait for the next inbound call.'}
            </div>
          ) : (
            turns.map((t, i) => {
              const isCaller = t.speaker === 'caller'
              return (
                <div key={i} className={`flex ${isCaller ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-[70%] rounded-2xl px-4 py-2 ${
                      isCaller
                        ? 'bg-brand-blue text-brand-light rounded-br-sm'
                        : 'bg-brand-light-gray text-brand-dark rounded-bl-sm'
                    }`}
                  >
                    <div className="text-xs opacity-70 mb-0.5">
                      {isCaller ? 'Caller' : 'Ron'} · {formatTime(t.ts)}
                    </div>
                    <div className="font-body leading-relaxed">{t.text}</div>
                  </div>
                </div>
              )
            })
          )}
          <div ref={transcriptEndRef} />
        </div>
      </div>
    </div>
  )
}
