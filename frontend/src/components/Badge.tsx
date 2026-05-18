import type { Status, Urgency } from '../types'

const URGENCY_CLASSES: Record<Urgency, string> = {
  urgent: 'bg-brand-orange text-brand-light',
  shopper: 'bg-brand-blue text-brand-light',
  unclear: 'bg-brand-mid text-brand-dark',
}

const STATUS_CLASSES: Record<Status, string> = {
  transferred: 'bg-brand-green text-brand-light',
  completed: 'bg-brand-light-gray text-brand-dark',
  // Escalated uses a desaturated orange (border + tinted bg) to stay on-brand
  // while reading distinctly from urgent's solid orange badge.
  escalated: 'bg-brand-orange/15 text-brand-orange border border-brand-orange/40',
  dropped: 'bg-brand-mid text-brand-dark',
}

const BASE = 'inline-block px-2 py-0.5 text-xs font-heading font-medium rounded-full uppercase tracking-wide'

export function UrgencyBadge({ value }: { value: Urgency }) {
  return <span className={`${BASE} ${URGENCY_CLASSES[value]}`}>{value}</span>
}

export function StatusBadge({ value }: { value: Status }) {
  return <span className={`${BASE} ${STATUS_CLASSES[value]}`}>{value}</span>
}
