import { useCallback, useState } from 'react'
import {
  type Accent,
  getAccent,
  getTheme,
  nextAccent,
  setAccent,
  setTheme,
  type Theme,
} from '@/lib/theme'

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(getTheme)
  const [accent, setAccentState] = useState<Accent>(getAccent)

  const toggle = useCallback(() => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    setThemeState(next)
  }, [theme])

  const cycleAccent = useCallback(() => {
    const next = nextAccent(accent)
    setAccent(next)
    setAccentState(next)
  }, [accent])

  return { theme, toggle, accent, cycleAccent }
}
