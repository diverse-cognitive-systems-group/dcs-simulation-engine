// Games list page at /games. Fetches available games from the API and renders
// them as cards. Clicking "Play" on a card navigates to the game setup page.

import { createRoute, redirect, useNavigate } from '@tanstack/react-router'
import { useListGamesEndpointApiGamesListGet } from '@/api/generated'
import { ThemeToggle } from '@/components/theme-toggle'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { clearAuth, getActiveExperimentName, getFullName } from '@/lib/auth'
import { unwrapOrvalData } from '@/lib/orval-response'
import { getServerConfig, peekServerConfig } from '@/lib/server-config'
import { requireAuth, rootRoute } from '../__root'

function GamesPage() {
  const navigate = useNavigate()
  const fullName = getFullName()
  const freePlay = peekServerConfig()?.mode === 'free_play'

  async function handleLogout() {
    clearAuth()
    await navigate({ to: '/login' })
  }

  const { data, isLoading, isError } = useListGamesEndpointApiGamesListGet()
  const games =
    unwrapOrvalData<{ games: Array<{ name: string; author: string; description: string | null }> }>(
      data,
    )?.games ?? []

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-muted-foreground">Loading games…</p>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-destructive">Failed to load games.</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background p-8">
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            {!freePlay && fullName && (
              <p className="text-muted-foreground mb-1">Hello, {fullName}!</p>
            )}
            <h1 className="text-2xl font-semibold">Games</h1>
          </div>
          <div className="flex items-center gap-2">
            {!freePlay && (
              <Button variant="ghost" size="sm" onClick={handleLogout}>
                Logout
              </Button>
            )}
            <ThemeToggle />
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          {games.map((game) => (
            <Card key={game.name} className="flex flex-col">
              <CardHeader className="flex-1">
                <CardTitle className="text-lg">{game.name}</CardTitle>
                <Badge variant="outline" className="w-fit text-xs">
                  {game.author}
                </Badge>
                {game.description && (
                  <CardDescription className="mt-2">{game.description}</CardDescription>
                )}
              </CardHeader>
              <CardFooter>
                <Button
                  className="w-full"
                  onClick={() =>
                    navigate({ to: '/games/$gameName', params: { gameName: game.name } })
                  }
                >
                  Play
                </Button>
              </CardFooter>
            </Card>
          ))}
        </div>
      </div>
    </div>
  )
}

export const gamesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/games',
  beforeLoad: async () => {
    const serverConfig = await getServerConfig()
    if (serverConfig.authentication_required) {
      await requireAuth()
    }
    if (serverConfig.mode === 'free_play') {
      return
    }
    const experimentName = getActiveExperimentName()
    if (experimentName) {
      throw redirect({
        to: '/experiments/$experimentName',
        params: { experimentName },
      })
    }
    if (serverConfig.default_experiment_name) {
      throw redirect({
        to: '/experiments/$experimentName',
        params: { experimentName: serverConfig.default_experiment_name },
      })
    }
  },
  component: GamesPage,
})
