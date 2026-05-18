import type { UrgencyFilter } from '../types'

const OPTIONS: { value: UrgencyFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'urgent', label: 'Urgent' },
  { value: 'shopper', label: 'Shopper' },
  { value: 'unclear', label: 'Unclear' },
]

interface Props {
  value: UrgencyFilter
  onChange: (next: UrgencyFilter) => void
}

export function FilterChips({ value, onChange }: Props) {
  return (
    <div className="flex gap-2">
      {OPTIONS.map((opt) => {
        const selected = opt.value === value
        return (
          <button
            key={opt.value}
            onClick={() => onChange(opt.value)}
            className={`px-3 py-1 text-sm font-heading rounded-full border transition-colors ${
              selected
                ? 'bg-brand-dark text-brand-light border-brand-dark'
                : 'bg-brand-light text-brand-dark border-brand-mid hover:bg-brand-light-gray'
            }`}
          >
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}
