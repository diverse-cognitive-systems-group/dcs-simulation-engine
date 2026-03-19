const DEFAULT_DEV_API_PORT = '8000'

function getWebSocketBaseOrigin(): string {
  const configuredOrigin = import.meta.env.VITE_API_ORIGIN?.trim()
  if (configuredOrigin) {
    return configuredOrigin
  }

  if (import.meta.env.DEV) {
    return `${window.location.protocol}//${window.location.hostname}:${DEFAULT_DEV_API_PORT}`
  }

  return window.location.origin
}

export function resolveWebSocketUrl(path: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const url = new URL(normalizedPath, getWebSocketBaseOrigin())
  const usesSecureTransport = url.protocol === 'https:' || url.protocol === 'wss:'
  url.protocol = usesSecureTransport ? 'wss:' : 'ws:'
  return url.toString()
}
