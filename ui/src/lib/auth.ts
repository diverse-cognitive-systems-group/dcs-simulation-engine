// Stores and retrieves the player's auth credentials from sessionStorage.
// sessionStorage is tab-scoped: credentials are cleared automatically when the tab closes.

import { resolveApiUrl } from './api-url'

const KEY = 'dcs_api_key'
const PLAYER_ID_KEY = 'dcs_player_id'
const FULL_NAME_KEY = 'dcs_full_name'
const RUN_NAME_KEY = 'dcs_run_name'

export function getApiKey(): string | null {
  return sessionStorage.getItem(KEY)
}

export function setAuth(apiKey: string, playerId: string, fullName: string): void {
  sessionStorage.setItem(KEY, apiKey)
  sessionStorage.setItem(PLAYER_ID_KEY, playerId)
  sessionStorage.setItem(FULL_NAME_KEY, fullName)
}

export function clearAuth(): void {
  sessionStorage.removeItem(KEY)
  sessionStorage.removeItem(PLAYER_ID_KEY)
  sessionStorage.removeItem(FULL_NAME_KEY)
}

export function getPlayerId(): string | null {
  return sessionStorage.getItem(PLAYER_ID_KEY)
}

export function getFullName(): string | null {
  return sessionStorage.getItem(FULL_NAME_KEY)
}

export function isAuthenticated(): boolean {
  return getApiKey() !== null
}

export function getActiveRunName(): string | null {
  return sessionStorage.getItem(RUN_NAME_KEY)
}

export function setActiveRunName(runName: string): void {
  sessionStorage.setItem(RUN_NAME_KEY, runName)
}

export async function ensureAnonymousAuth(): Promise<void> {
  if (isAuthenticated()) return
  const response = await fetch(resolveApiUrl('/api/player/anonymous'), { method: 'POST' })
  if (!response.ok) {
    throw new Error(`Unable to create anonymous player (HTTP ${response.status})`)
  }
  const data = (await response.json()) as { api_key: string; player_id: string }
  setAuth(data.api_key, data.player_id, 'Anonymous')
}
