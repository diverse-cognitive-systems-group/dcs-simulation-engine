import { Moon, Palette, Sun } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useTheme } from '@/hooks/use-theme'

export function ThemeToggle() {
  const { theme, toggle, accent, cycleAccent } = useTheme()
  return (
    <div className="flex items-center gap-1">
      <Button
        variant="ghost"
        size="icon"
        onClick={cycleAccent}
        aria-label={`Cycle accent color (current: ${accent})`}
        title={`Accent: ${accent}`}
      >
        <Palette className="h-4 w-4 text-primary" />
      </Button>
      <Button variant="ghost" size="icon" onClick={toggle} aria-label="Toggle theme">
        {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      </Button>
    </div>
  )
}
