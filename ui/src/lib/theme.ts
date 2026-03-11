// Manages the dark/light theme by toggling the `dark` class on <html>.
// Persists the user's preference to localStorage.

const STORAGE_KEY = 'theme'
const ACCENT_STORAGE_KEY = 'accent'

const ACCENT_HUES = {
  violet: 293,
  indigo: 265,
  emerald: 160,
  amber: 85,
} as const

const DEFAULT_ACCENT: Accent = 'violet'

export type Theme = 'light' | 'dark'
export type Accent = keyof typeof ACCENT_HUES

function getSystemTheme(): Theme {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function getTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'dark' || stored === 'light') return stored
  return getSystemTheme()
}

export function setTheme(theme: Theme) {
  localStorage.setItem(STORAGE_KEY, theme)
  if (theme === 'dark') {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
}

function applyAccent(accent: Accent) {
  document.documentElement.style.setProperty('--accent-hue', String(ACCENT_HUES[accent]))
}

export function getAccent(): Accent {
  const stored = localStorage.getItem(ACCENT_STORAGE_KEY)
  if (stored && stored in ACCENT_HUES) return stored as Accent
  return DEFAULT_ACCENT
}

export function setAccent(accent: Accent) {
  localStorage.setItem(ACCENT_STORAGE_KEY, accent)
  applyAccent(accent)
}

export function nextAccent(accent: Accent): Accent {
  const accents = Object.keys(ACCENT_HUES) as Accent[]
  const current = accents.indexOf(accent)
  const nextIndex = (current + 1) % accents.length
  return accents[nextIndex]
}

export function initTheme() {
  setTheme(getTheme())
  setAccent(getAccent())
}
