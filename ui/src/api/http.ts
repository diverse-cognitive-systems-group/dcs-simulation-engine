// Thin wrapper around fetch that injects the Bearer token and throws on non-2xx responses.
// Used by TanStack Query hooks throughout the app instead of calling fetch directly.

import { getApiKey } from '../lib/auth'
import { resolveApiUrl } from '../lib/api-url'

export class HttpError extends Error {
  status: number
  detail: unknown

  constructor(message: string, status: number, detail: unknown) {
    super(message)
    this.name = 'HttpError'
    this.status = status
    this.detail = detail
  }
}

export async function httpClient<T>(url: string, options?: RequestInit): Promise<T> {
  const apiKey = getApiKey()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string>),
  }
  if (apiKey) {
    headers.Authorization = `Bearer ${apiKey}`
  }

  const response = await fetch(resolveApiUrl(url), { ...options, headers })

  if (!response.ok) {
    // Try to surface the FastAPI `detail` field; fall back to the HTTP status text.
    const body = await response.json().catch(() => ({ detail: response.statusText }))
    const detail = body?.detail
    const message =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join('; ')
          : `HTTP ${response.status}`
    throw new HttpError(message, response.status, detail)
  }

  return response.json() as Promise<T>
}
