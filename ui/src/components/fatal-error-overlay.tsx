// Full-screen overlay for unrecoverable errors (e.g. fatal WebSocket failures).
// Blocks all interaction and provides a single action to return to the games list.

import { Button } from '@/components/ui/button'

interface FatalErrorOverlayProps {
  message: string
  onReturn: () => void
}

export function FatalErrorOverlay({ message, onReturn }: FatalErrorOverlayProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
      <div className="flex flex-col items-center gap-4 rounded-lg border bg-card p-8 shadow-lg max-w-sm w-full mx-4 text-center">
        <h2 className="text-lg font-semibold text-destructive">Connection Lost</h2>
        <p className="text-sm text-muted-foreground">{message}</p>
        <Button onClick={onReturn} className="w-full">
          Return to Games
        </Button>
      </div>
    </div>
  )
}
