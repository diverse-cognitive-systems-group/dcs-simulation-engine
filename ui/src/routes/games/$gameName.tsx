// Game setup page at /games/:gameName. Lets the player choose player and simulator characters,
// then POSTs to create a session and navigates to the play view.

import { useQuery } from '@tanstack/react-query'
import { createRoute, redirect, useNavigate, useParams } from '@tanstack/react-router'
import { useEffect, useMemo, useState } from 'react'
import { useCreateGameApiPlayGamePost } from '@/api/generated'
import { HttpError, httpClient } from '@/api/http'
import { FatalErrorOverlay } from '@/components/fatal-error-overlay'
import { ThemeToggle } from '@/components/theme-toggle'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { getApiKey } from '@/lib/auth'
import { unwrapOrvalData } from '@/lib/orval-response'
import { getServerConfig } from '@/lib/server-config'
import { requireAuth, rootRoute } from '../__root'

function resumeStorageKey(gameName: string) {
  return `dcs_resume_${gameName}`
}

function getSavedSessionId(gameName: string): string | null {
  return localStorage.getItem(resumeStorageKey(gameName))
}

function saveSessionId(gameName: string, sessionId: string) {
  localStorage.setItem(resumeStorageKey(gameName), sessionId)
}

function clearSavedSessionId(gameName: string) {
  localStorage.removeItem(resumeStorageKey(gameName))
}

interface CharacterChoice {
  hid: string
  label: string
}

interface GameSetupOptionsResponse {
  game: string
  allowed: boolean
  can_start: boolean
  denial_reason: 'not_allowed' | 'no_valid_pc' | 'no_valid_npc' | null
  message: string | null
  pcs: CharacterChoice[]
  npcs: CharacterChoice[]
}

interface CharactersListResponse {
  characters: Array<{
    hid: string
    short_description: string
  }>
}

function randomPick<T>(arr: T[]): T | undefined {
  if (!arr.length) return undefined
  return arr[Math.floor(Math.random() * arr.length)]
}

function GameSetupPage() {
  const { gameName } = useParams({ from: '/games/$gameName' })
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const [fatalError, setFatalError] = useState<string | null>(null)
  const [resumableSessionId, setResumableSessionId] = useState<string | null>(null)

  // On mount, check if a paused session exists for this game.
  useEffect(() => {
    const savedId = getSavedSessionId(gameName)
    if (!savedId) return
    httpClient<{ status: string }>(`/api/sessions/${savedId}/status`)
      .then((data) => {
        if (data.status === 'paused') {
          setResumableSessionId(savedId)
        } else {
          clearSavedSessionId(gameName)
        }
      })
      .catch(() => {
        // Session gone or server unreachable — clear stale entry.
        clearSavedSessionId(gameName)
      })
  }, [gameName])

  const {
    data: setupData,
    isLoading: setupLoading,
    isError: setupIsError,
    error: setupError,
  } = useQuery({
    queryKey: ['play-setup', gameName],
    queryFn: () =>
      httpClient<GameSetupOptionsResponse>(`/api/play/setup/${encodeURIComponent(gameName)}`),
  })

  const { data: charactersData } = useQuery({
    queryKey: ['characters-list'],
    queryFn: () => httpClient<CharactersListResponse>('/api/characters/list'),
  })

  const characterDescriptions = useMemo(() => {
    const map = new Map<string, string>()
    for (const character of charactersData?.characters ?? []) {
      const description = character.short_description?.trim()
      if (description) map.set(character.hid, description)
    }
    return map
  }, [charactersData?.characters])

  const pcs = useMemo(() => {
    return (setupData?.pcs ?? []).map((choice) => ({
      hid: choice.hid,
      description: characterDescriptions.get(choice.hid) ?? null,
    }))
  }, [setupData?.pcs, characterDescriptions])

  const npcs = useMemo(() => {
    return (setupData?.npcs ?? []).map((choice) => ({
      hid: choice.hid,
      description: characterDescriptions.get(choice.hid) ?? null,
    }))
  }, [setupData?.npcs, characterDescriptions])

  // biome-ignore lint/correctness/useExhaustiveDependencies: intentional — re-pick only when list size changes
  const defaultPc = useMemo(() => randomPick(pcs)?.hid ?? '', [pcs.length])
  // biome-ignore lint/correctness/useExhaustiveDependencies: intentional — re-pick only when list size changes
  const defaultNpc = useMemo(() => randomPick(npcs)?.hid ?? '', [npcs.length])

  const [pcChoice, setPcChoice] = useState<string>('')
  const [npcChoice, setNpcChoice] = useState<string>('')

  // Fall back to a random default if the user hasn't made an explicit selection.
  const resolvedPc = pcChoice || defaultPc
  const resolvedNpc = npcChoice || defaultNpc
  const selectedPc = pcs.find((choice) => choice.hid === resolvedPc) ?? null
  const selectedNpc = npcs.find((choice) => choice.hid === resolvedNpc) ?? null

  const { mutate: createGame, isPending } = useCreateGameApiPlayGamePost({
    mutation: {
      onSuccess: async (response) => {
        const result = unwrapOrvalData<{ session_id: string }>(response)
        if (!result?.session_id) {
          setError('Failed to start game')
          return
        }
        saveSessionId(gameName, result.session_id)
        await navigate({
          to: '/play/$sessionId',
          params: { sessionId: result.session_id },
          search: { gameName, experimentName: '' },
        })
      },
      onError: (err) => {
        if (err instanceof HttpError && err.status >= 500) {
          setFatalError('Unable to start the session right now. Please return and try again.')
          return
        }
        setError(err instanceof Error ? err.message : 'Failed to start game')
      },
    },
  })

  async function handleReturnToGames() {
    await navigate({ to: '/games' })
  }

  async function handleResume() {
    if (!resumableSessionId) return
    await navigate({
      to: '/play/$sessionId',
      params: { sessionId: resumableSessionId },
      search: { gameName, experimentName: '' },
    })
  }

  function handleNewGame() {
    clearSavedSessionId(gameName)
    setResumableSessionId(null)
    startGame()
  }

  function startGame() {
    if (!setupData?.can_start) return
    setError(null)
    createGame({
      data: {
        api_key: getApiKey() || undefined,
        game: gameName,
        pc_choice: resolvedPc || null,
        npc_choice: resolvedNpc || null,
      },
    })
  }

  if (fatalError || (setupIsError && setupError instanceof HttpError && setupError.status >= 500)) {
    return (
      <div className="min-h-screen bg-background">
        <FatalErrorOverlay
          message={fatalError ?? 'Unable to load setup details right now. Please try again.'}
          onReturn={handleReturnToGames}
        />
      </div>
    )
  }

  if (setupLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-4">
        <Card className="w-full max-w-md">
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Loading setup options…</p>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (setupIsError || !setupData) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-4">
        <div className="fixed top-3 right-3">
          <ThemeToggle />
        </div>
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>Setup Unavailable</CardTitle>
            <CardDescription>We couldn&apos;t prepare this game right now.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Alert variant="destructive">
              <AlertDescription>
                {setupError instanceof Error ? setupError.message : 'Failed to load setup options'}
              </AlertDescription>
            </Alert>
            <Button className="w-full" onClick={handleReturnToGames}>
              Back to Games
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (!setupData.allowed || !setupData.can_start) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-4">
        <div className="fixed top-3 right-3">
          <ThemeToggle />
        </div>
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>{setupData.game}</CardTitle>
            <CardDescription>Setup is blocked for this account.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Alert variant="destructive">
              <AlertDescription>
                {setupData.message ?? 'You cannot start this game with your current access.'}
              </AlertDescription>
            </Alert>
            <Button className="w-full" onClick={handleReturnToGames}>
              Back to Games
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="fixed top-3 right-3">
        <ThemeToggle />
      </div>
      <Card className="w-full max-w-lg sm:min-h-[34rem]">
        <CardHeader>
          <CardTitle>{setupData.game}</CardTitle>
          <CardDescription>Set up your session before starting.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-7 pb-8">
          {pcs.length > 0 && (
            <div className="space-y-2">
              <Label>Player Character</Label>
              <Select value={resolvedPc} onValueChange={(v) => setPcChoice(v ?? '')}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Choose your character" />
                </SelectTrigger>
                <SelectContent>
                  {pcs.map((c) => (
                    <SelectItem key={c.hid} value={c.hid}>
                      {c.hid}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <div className="rounded-md border border-input/70 bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
                {selectedPc?.description ?? 'No description available for this character.'}
              </div>
            </div>
          )}

          {npcs.length > 0 && (
            <div className="space-y-2">
              <Label>Simulator Character</Label>
              <Select value={resolvedNpc} onValueChange={(v) => setNpcChoice(v ?? '')}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Choose a simulator character" />
                </SelectTrigger>
                <SelectContent>
                  {npcs.map((c) => (
                    <SelectItem key={c.hid} value={c.hid}>
                      {c.hid}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <div className="rounded-md border border-input/70 bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
                {selectedNpc?.description ?? 'No description available for this character.'}
              </div>
            </div>
          )}

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {resumableSessionId ? (
            <>
              <Button className="w-full" onClick={handleResume}>
                Resume Game
              </Button>
              <Button
                variant="outline"
                className="w-full"
                onClick={handleNewGame}
                disabled={isPending || !setupData.can_start}
              >
                {isPending ? 'Starting…' : 'New Game'}
              </Button>
            </>
          ) : (
            <Button
              className="w-full"
              onClick={startGame}
              disabled={isPending || !setupData.can_start}
            >
              {isPending ? 'Starting…' : 'Play'}
            </Button>
          )}

          <Button variant="outline" className="w-full" onClick={() => navigate({ to: '/games' })}>
            Back to Games
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}

export const gameSetupRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/games/$gameName',
  beforeLoad: async () => {
    const serverConfig = await getServerConfig()
    if (serverConfig.authentication_required) {
      await requireAuth()
    }
    throw redirect({ to: '/run' })
  },
  component: GameSetupPage,
})
