function isAbsoluteUrl(value: string): boolean {
  return /^https?:\/\//.test(value)
}

function getApiBaseOrigin(): string | null {
  const configuredOrigin = import.meta.env.VITE_API_ORIGIN?.trim()
  if (configuredOrigin) {
    return configuredOrigin
  }

  if (import.meta.env.DEV) {
    return null
  }

  return window.location.origin
}

export function resolveApiUrl(path: string): string {
  if (isAbsoluteUrl(path)) {
    return path
  }

  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const baseOrigin = getApiBaseOrigin()
  if (!baseOrigin) {
    return normalizedPath
  }

  return new URL(normalizedPath, baseOrigin).toString()
}
