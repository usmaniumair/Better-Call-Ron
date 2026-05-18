export type Urgency = 'urgent' | 'shopper' | 'unclear'
export type Status = 'transferred' | 'escalated' | 'dropped' | 'completed'

export interface Turn {
  speaker: 'caller' | 'agent'
  text: string
  ts: string
}

export interface ToolInvocation {
  name: string
  input: Record<string, unknown>
  result: Record<string, unknown>
  ts: string
}

export interface ActiveCall {
  call_id: string
  turn_count: number
  started_at: string | null
  urgency: Urgency
  status: Status
}

export interface CallSummary {
  call_id: string
  from_number: string
  started_at: string | null
  ended_at: string | null
  urgency: Urgency
  status: Status
  turn_count: number
}

export interface CallRecord extends CallSummary {
  turns: Turn[]
  tool_log: ToolInvocation[]
}

export interface Jurisdiction {
  state: string
  county?: string | null
}

export interface EmergencyContact {
  name: string
  relationship: string
  phone: string
}

export interface User {
  id: string
  name: string
  date_of_birth: string
  phone_numbers: string[]
  email: string | null
  payment_method_token: string
  emergency_contacts: EmergencyContact[]
  budget_max_hourly: number
  budget_max_retainer: number
  preferred_language: string
  home_jurisdiction: Jurisdiction
  notes: string
}

export interface LawyerJurisdiction {
  state: string
  counties: string[]
}

export type AvailabilityStatus = 'now' | 'business_hours' | 'unavailable'

export interface Lawyer {
  id: string
  name: string
  firm: string
  bar_state: string
  practice_areas: string[]
  jurisdictions: LawyerJurisdiction[]
  hourly_rate: number
  flat_consult_rate: number | null
  typical_retainer: number | null
  availability_status: AvailabilityStatus
  accepts_emergencies: boolean
  languages: string[]
  phone: string
  email: string | null
  years_experience: number
  rating: number
  notes: string
}

export type TabKey = 'live' | 'history' | 'users' | 'lawyers'

export type UrgencyFilter = Urgency | 'all'
