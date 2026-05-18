// Mirrors src/server.py:_pretty_practice_area but title-cases for table display
// (the backend version is for spoken/SMS output and stays lowercase).
const SPECIAL_CASE_UPPER = new Set(['dui'])

export function prettyPracticeArea(raw: string): string {
  const normalized = (raw || '').replace(/_/g, ' ').trim()
  if (!normalized) return ''
  if (SPECIAL_CASE_UPPER.has(normalized.toLowerCase())) return normalized.toUpperCase()
  return normalized.charAt(0).toUpperCase() + normalized.slice(1)
}

export function prettyPracticeAreas(raw: string[]): string {
  return raw.map(prettyPracticeArea).join(', ')
}
