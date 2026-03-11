// Orval can type responses as `{ data, status }`, while our custom mutator returns raw JSON.
// This helper normalizes both shapes so route code stays runtime-safe.

export function unwrapOrvalData<T>(response: unknown): T | null {
  if (response === null || response === undefined) return null

  if (typeof response !== 'object') return null

  const record = response as Record<string, unknown>
  if ('data' in record && record.data !== null && record.data !== undefined) {
    return record.data as T
  }

  return response as T
}
