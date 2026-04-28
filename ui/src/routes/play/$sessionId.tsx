// Live play page at /play/:sessionId. Connects to the game session via WebSocket,
// renders the chat transcript, and lets the player submit turns.

import { createRoute, useNavigate, useParams, useSearch } from '@tanstack/react-router'
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  useClearSessionEventFeedbackApiSessionsSessionIdEventsEventIdFeedbackDelete,
  useSubmitSessionEventFeedbackApiSessionsSessionIdEventsEventIdFeedbackPost,
} from '@/api/generated'
import type { SubmitSessionEventFeedbackResponse } from '@/api/generated/model'
import { HttpError } from '@/api/http'
import { ChatMessageBubble } from '@/components/chat-message'
import { FatalErrorOverlay } from '@/components/fatal-error-overlay'
import { ThemeToggle } from '@/components/theme-toggle'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import type { MessageFeedback } from '@/hooks/use-session-websocket'
import { useSessionWebSocket } from '@/hooks/use-session-websocket'
import { unwrapOrvalData } from '@/lib/orval-response'
import { getServerConfig } from '@/lib/server-config'
import { cn } from '@/lib/utils'
import { requireAuth, rootRoute } from '../__root'

// TODO: We should probably have a shared config file for both server and UI
const MAX_INPUT_LENGTH = 350

interface CommandSuggestion {
  command: string
  description: string
}

const GAME_COMMANDS: Record<string, CommandSuggestion[]> = {
  explore: [
    { command: '/help', description: 'Show instructions.' },
    { command: '/abilities', description: 'Show character abilities.' },
    { command: '/finish', description: 'Finish the game.' },
  ],
  goalhorizon: [
    { command: '/help', description: 'Show instructions.' },
    { command: '/abilities', description: 'Show character abilities.' },
    {
      command: '/finish',
      description:
        "Submit your prediction about the simulator character's capabilities and finish the game.",
    },
  ],
  inferintent: [
    { command: '/help', description: 'Show instructions.' },
    { command: '/abilities', description: 'Show character abilities.' },
    {
      command: '/finish',
      description: "Submit your prediction about the character's intent and finish the game.",
    },
  ],
  foresight: [
    { command: '/help', description: 'Show instructions.' },
    { command: '/abilities', description: 'Show character abilities.' },
    { command: '/finish', description: 'Finish the game.' },
  ],
  teamwork: [
    { command: '/help', description: 'Show instructions.' },
    { command: '/abilities', description: 'Show character abilities.' },
    { command: '/finish', description: 'Finish the game.' },
  ],
}

function normalizeGameName(value: string): string {
  return value.replace(/[\s_-]+/g, '').toLowerCase()
}

function formatElapsed(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function PlayPage() {
  const { sessionId } = useParams({ from: '/play/$sessionId' })
  const { gameName, experimentName } = useSearch({ from: '/play/$sessionId' })
  const navigate = useNavigate()
  // useSessionWebSocket opens the WebSocket connection and returns reactive state plus
  // action callbacks; see hooks/use-session-websocket.ts for the protocol details.
  const {
    messages,
    wsState,
    turns,
    exited,
    waiting,
    isReplaying,
    pcHid,
    npcHid,
    hasGameFeedback,
    sendTurn,
    setMessageFeedback,
  } = useSessionWebSocket(sessionId)

  const [input, setInput] = useState('')
  const [feedbackPendingEventId, setFeedbackPendingEventId] = useState<string | null>(null)
  const [selectedCommandIndex, setSelectedCommandIndex] = useState(0)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const startTimeRef = useRef(Date.now())
  // bottomRef is attached to a sentinel div at the end of the message list so we can
  // scroll it into view whenever a new message arrives.
  const bottomRef = useRef<HTMLDivElement>(null)

  const { mutateAsync: submitMessageFeedback } =
    useSubmitSessionEventFeedbackApiSessionsSessionIdEventsEventIdFeedbackPost()
  const { mutateAsync: clearMessageFeedback } =
    useClearSessionEventFeedbackApiSessionsSessionIdEventsEventIdFeedbackDelete()

  // biome-ignore lint/correctness/useExhaustiveDependencies: intentional — scroll on both new messages and waiting-state change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, waiting])

  // Elapsed timer — counts up every second until the session ends.
  const sessionEnded = wsState === 'closed' || exited
  useEffect(() => {
    if (sessionEnded) return
    const id = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startTimeRef.current) / 1000))
    }, 1000)
    return () => clearInterval(id)
  }, [sessionEnded])

  const availableCommands = useMemo(() => {
    return GAME_COMMANDS[normalizeGameName(gameName ?? '')] ?? []
  }, [gameName])

  const commandSuggestions = useMemo(() => {
    if (!input.startsWith('/')) return []
    if (/\s/.test(input.slice(1))) return []

    const query = input.toLowerCase()
    return availableCommands.filter((item) => item.command.startsWith(query))
  }, [availableCommands, input])

  useEffect(() => {
    if (!commandSuggestions.length) {
      setSelectedCommandIndex(0)
      return
    }
    setSelectedCommandIndex((current) => Math.min(current, commandSuggestions.length - 1))
  }, [commandSuggestions])

  function submitInput() {
    const text = input.trim()
    if (!text || exited || wsState !== 'ready' || waiting) return
    sendTurn(text)
    setInput('')
  }

  function applyCommandSuggestion(suggestion: CommandSuggestion) {
    setInput(`${suggestion.command} `)
  }

  function handleSubmit(e: React.SubmitEvent) {
    e.preventDefault()
    submitInput()
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (commandSuggestions.length) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelectedCommandIndex((current) => (current + 1) % commandSuggestions.length)
        return
      }

      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelectedCommandIndex((current) =>
          current === 0 ? commandSuggestions.length - 1 : current - 1,
        )
        return
      }

      const selectedSuggestion = commandSuggestions[selectedCommandIndex] ?? commandSuggestions[0]
      const typedCommand = input.trim().toLowerCase()
      const canAutocompleteWithEnter =
        selectedSuggestion && typedCommand !== selectedSuggestion.command

      if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey && canAutocompleteWithEnter)) {
        e.preventDefault()
        if (selectedSuggestion) {
          applyCommandSuggestion(selectedSuggestion)
        }
        return
      }
    }

    // Enter alone submits; Shift+Enter inserts a newline.
    const canSubmit = !waiting && !exited && wsState === 'ready' && !!input.trim()
    if (e.key === 'Enter' && !e.shiftKey && canSubmit) {
      e.preventDefault()
      submitInput()
    }
  }

  async function handleClose() {
    if (experimentName) {
      await navigate({ to: '/run' })
      return
    }
    await navigate({ to: '/games' })
  }

  async function handleSubmitFeedback(payload: {
    eventId: string
    liked: boolean
    comment: string
    doesntMakeSense: boolean
    outOfCharacter: boolean
    other: boolean
  }): Promise<MessageFeedback> {
    setFeedbackPendingEventId(payload.eventId)

    try {
      const response = await submitMessageFeedback({
        sessionId,
        eventId: payload.eventId,
        data: {
          liked: payload.liked,
          comment: payload.comment,
          doesnt_make_sense: payload.doesntMakeSense,
          out_of_character: payload.outOfCharacter,
          other: payload.other,
        },
      })
      const result = unwrapOrvalData<SubmitSessionEventFeedbackResponse>(response)
      if (!result?.feedback) {
        throw new Error('Feedback save did not return stored feedback.')
      }

      const feedback: MessageFeedback = {
        liked: result.feedback.liked,
        comment: result.feedback.comment ?? '',
        doesntMakeSense: result.feedback.doesnt_make_sense,
        outOfCharacter: result.feedback.out_of_character,
        other: result.feedback.other ?? false,
        submittedAt: result.feedback.submitted_at,
      }
      setMessageFeedback(payload.eventId, feedback)
      return feedback
    } catch (error) {
      if (error instanceof HttpError) {
        throw new Error(error.message)
      }
      throw error instanceof Error ? error : new Error('Failed to save feedback.')
    } finally {
      setFeedbackPendingEventId((current) => (current === payload.eventId ? null : current))
    }
  }

  async function handleClearFeedback(eventId: string): Promise<void> {
    setFeedbackPendingEventId(eventId)

    try {
      await clearMessageFeedback({
        sessionId,
        eventId,
      })
      setMessageFeedback(eventId, undefined)
    } catch (error) {
      if (error instanceof HttpError) {
        throw new Error(error.message)
      }
      throw error instanceof Error ? error : new Error('Failed to clear feedback.')
    } finally {
      setFeedbackPendingEventId((current) => (current === eventId ? null : current))
    }
  }

  const isConnecting = wsState === 'connecting' || wsState === 'auth'
  const isError = wsState === 'error'
  const isClosed = wsState === 'closed' || exited
  // Allow drafting at all times except terminal states (closed/error).
  const inputDisabled = isClosed || isError

  // Send is blocked while the simulation is loading or awaiting the next turn response.
  // turns === 0 means the initial simulator message hasn't arrived yet (game not started).
  const sendDisabled = !input.trim() || inputDisabled || isConnecting || waiting || turns === 0

  return (
    <div className="h-screen flex flex-col bg-background">
      <header className="border-b px-4 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="font-semibold text-sm">{gameName || 'Game'}</h1>
          <Badge variant="outline" className="text-xs">
            Turn {turns}
          </Badge>
          <Badge variant="outline" className="text-xs tabular-nums">
            {formatElapsed(elapsedSeconds)}
          </Badge>
          {pcHid && (
            <Badge variant="secondary" className="text-xs" title="Your character">
              Player Character: {pcHid}
            </Badge>
          )}
          {npcHid && (
            <Badge variant="secondary" className="text-xs" title="Simulator character">
              Simulator Character: {npcHid}
            </Badge>
          )}
          {isClosed && (
            <Badge variant="secondary" className="text-xs">
              Ended
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className="mx-auto w-full max-w-[96vw] sm:max-w-[92vw] lg:max-w-[86vw] xl:max-w-[80vw] space-y-3">
          {(isConnecting || (turns === 0 && wsState === 'ready')) && (
            <div className="flex flex-col items-center gap-3 py-8 text-muted-foreground">
              {/* CSS-only spinner: a bordered circle with one colored arc, rotated by animation */}
              <div className="w-6 h-6 rounded-full border-2 border-muted/70 border-t-primary animate-spin" />
              <p className="text-sm italic">Loading simulation environment…</p>
            </div>
          )}

          {isError && (
            <FatalErrorOverlay
              message="Connection error. Please close and try again."
              onReturn={handleClose}
            />
          )}

          {messages.map((msg, idx) => {
            // Insert a "Session resumed" separator between the last historical message
            // and the first live message, once replay has completed.
            const isLastHistorical =
              !isReplaying &&
              msg.isHistorical &&
              (idx === messages.length - 1 || !messages[idx + 1].isHistorical)
            return (
              <div key={msg.id} className={msg.isHistorical ? 'opacity-60' : undefined}>
                <ChatMessageBubble
                  message={msg}
                  feedbackPending={!!msg.eventId && feedbackPendingEventId === msg.eventId}
                  onSubmitFeedback={handleSubmitFeedback}
                  onClearFeedback={handleClearFeedback}
                />
                {isLastHistorical && (
                  <div className="flex items-center gap-3 py-3 text-xs text-muted-foreground">
                    <div className="flex-1 border-t border-dashed" />
                    <span>Session resumed</span>
                    <div className="flex-1 border-t border-dashed" />
                  </div>
                )}
              </div>
            )
          })}

          {/* Animated "thinking" indicator shown while waiting for the AI response */}
          {waiting && (
            <div className="flex justify-start">
              <div className="bg-muted rounded-2xl rounded-bl-sm px-4 py-3 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:0ms]" />
                <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:150ms]" />
                <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:300ms]" />
              </div>
            </div>
          )}

          {exited && (
            <div className="flex flex-col items-center gap-3 py-4 text-center">
              <div>
                <Badge variant="secondary">Simulation ended</Badge>
              </div>
              {hasGameFeedback && (
                <Button className="mx-auto">Continue to Post Game Feedback</Button>
              )}
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      <form onSubmit={handleSubmit} className="border-t px-4 py-3 flex gap-2 items-end shrink-0">
        <div className="relative flex-1 space-y-1">
          {commandSuggestions.length > 0 && (
            <div className="absolute inset-x-0 bottom-full z-20 mb-2 overflow-hidden rounded-xl border border-border bg-card shadow-lg">
              <div className="border-b border-border/70 px-3 py-2 text-xs text-muted-foreground">
                Slash commands
              </div>
              <div className="max-h-56 overflow-y-auto py-1">
                {commandSuggestions.map((suggestion, index) => (
                  <button
                    key={suggestion.command}
                    type="button"
                    className={cn(
                      'flex w-full items-start justify-between gap-3 px-3 py-2 text-left transition-colors',
                      index === selectedCommandIndex ? 'bg-primary/10' : 'hover:bg-muted/60',
                    )}
                    onMouseDown={(event) => {
                      event.preventDefault()
                      applyCommandSuggestion(suggestion)
                    }}
                    onMouseEnter={() => setSelectedCommandIndex(index)}
                  >
                    <span className="font-mono text-sm">{suggestion.command}</span>
                    <span className="text-xs text-muted-foreground">{suggestion.description}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value.slice(0, MAX_INPUT_LENGTH))}
            onKeyDown={handleKeyDown}
            placeholder={isClosed ? 'Session ended.' : 'What do you do next?'}
            disabled={inputDisabled}
            rows={2}
            className="resize-none"
            autoFocus
          />
          <p className="text-xs text-muted-foreground text-right">
            {input.length}/{MAX_INPUT_LENGTH}
          </p>
        </div>
        <Button type="submit" className="self-center" disabled={sendDisabled}>
          Send
        </Button>
      </form>
    </div>
  )
}

export const playRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/play/$sessionId',
  validateSearch: (search: Record<string, unknown>) => ({
    gameName: typeof search.gameName === 'string' ? search.gameName : '',
    experimentName: typeof search.experimentName === 'string' ? search.experimentName : '',
  }),
  beforeLoad: async () => {
    const serverConfig = await getServerConfig()
    if (serverConfig.authentication_required) {
      await requireAuth()
    }
  },
  component: PlayPage,
})
