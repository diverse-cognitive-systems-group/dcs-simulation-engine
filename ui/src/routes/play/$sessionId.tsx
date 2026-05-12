// Live play page at /play/:sessionId. Connects to the game session via WebSocket,
// renders the chat transcript, and lets the player submit turns.

import { useQuery } from '@tanstack/react-query'
import { createRoute, useNavigate, useParams, useSearch } from '@tanstack/react-router'
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  useClearSessionEventFeedbackApiSessionsSessionIdEventsEventIdFeedbackDelete,
  useSubmitSessionEventFeedbackApiSessionsSessionIdEventsEventIdFeedbackPost,
} from '@/api/generated'
import type { SubmitSessionEventFeedbackResponse } from '@/api/generated/model'
import { HttpError, httpClient } from '@/api/http'
import { ChatMessageBubble } from '@/components/chat-message'
import { FatalErrorOverlay } from '@/components/fatal-error-overlay'
import { ThemeToggle } from '@/components/theme-toggle'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import type { ChatMessage, EventType, MessageFeedback } from '@/hooks/use-session-websocket'
import { useSessionWebSocket } from '@/hooks/use-session-websocket'
import { ensureAnonymousAuth } from '@/lib/auth'
import { unwrapOrvalData } from '@/lib/orval-response'
import { getServerConfig } from '@/lib/server-config'
import { cn } from '@/lib/utils'
import { requireAuth, rootRoute } from '../__root'

// TODO: We should probably have a shared config file for both server and UI
const MAX_INPUT_LENGTH = 350
const THINKING_MESSAGE_INTERVAL_MS = 6000
const LONG_THINKING_MESSAGE_DELAY_MS = 15000
const THINKING_MESSAGES = [
  'Evaluating context',
  'Considering objectives',
  'Resolving character decisions',
  'Projecting outcomes',
  'Weighing possibilities',
  'Tracing likely reactions',
  'Checking implications',
  'Balancing constraints',
  'Synthesizing results',
  'Reviewing the situation',
  'Mapping next steps',
  'Reconciling details',
  'Estimating consequences',
  'Comparing possible paths',
  'Drawing the threads together',
]
const LONG_THINKING_MESSAGES = [
  'Still working through the possibilities',
  'Taking a little longer to reason this through',
  'Checking the details carefully',
  'Resolving a complex turn',
  'Working through a few more details',
  'Spending extra time on this one',
  'Keeping at it',
  'Almost there',
]

interface CommandSuggestion {
  command: string
  description: string
}

interface ReconstructionSession {
  session_id?: string
  status?: string
  game_name?: string
  pc_hid?: string | null
  npc_hid?: string | null
  turns_completed?: number | null
}

interface ReconstructionFeedback {
  liked?: boolean
  comment?: string | null
  doesnt_make_sense?: boolean
  out_of_character?: boolean
  other?: boolean
  submitted_at?: string
}

interface ReconstructionEvent {
  seq?: number
  event_id?: string
  event_ts?: string
  direction?: string
  event_type?: string
  content?: string
  turn_index?: number
  visible_to_user?: boolean
  feedback?: ReconstructionFeedback | null
}

interface SessionReconstruction {
  session?: ReconstructionSession
  events?: ReconstructionEvent[]
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
      command: '/new-scene',
      description: 'Start a new scene (characters retain memory of prior scenes).',
    },
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

function isTerminalSessionStatus(status: string | undefined): boolean {
  return status === 'closed' || status === 'error'
}

function feedbackFromReconstruction(
  feedback: ReconstructionFeedback | null | undefined,
): MessageFeedback | undefined {
  if (!feedback || typeof feedback.liked !== 'boolean') return undefined
  return {
    liked: feedback.liked,
    comment: feedback.comment ?? '',
    doesntMakeSense: Boolean(feedback.doesnt_make_sense),
    outOfCharacter: Boolean(feedback.out_of_character),
    other: Boolean(feedback.other),
    submittedAt: feedback.submitted_at ?? new Date().toISOString(),
  }
}

function eventTypeFromReconstruction(event: ReconstructionEvent): EventType {
  const eventType = String(event.event_type ?? 'info').toLowerCase()
  const direction = String(event.direction ?? 'outbound').toLowerCase()

  if (eventType === 'message') return direction === 'inbound' ? 'info' : 'ai'
  if (eventType === 'error') return 'error'
  if (eventType === 'warning') return 'warning'
  return 'info'
}

function messagesFromReconstruction(
  reconstruction: SessionReconstruction | undefined,
): ChatMessage[] {
  return (reconstruction?.events ?? [])
    .filter((event) => {
      const eventType = String(event.event_type ?? '').toLowerCase()
      if (event.visible_to_user === false) return false
      return !['session_start', 'session_end'].includes(eventType)
    })
    .map((event, index) => {
      const direction = String(event.direction ?? 'outbound').toLowerCase()
      return {
        id: event.event_id ?? `${event.seq ?? index}`,
        role: direction === 'inbound' ? 'user' : 'ai',
        eventType: eventTypeFromReconstruction(event),
        content: event.content ?? '',
        eventId: event.event_id,
        feedback: feedbackFromReconstruction(event.feedback),
        timestamp: event.event_ts ? new Date(event.event_ts).getTime() : Date.now(),
      }
    })
}

function turnsFromReconstruction(reconstruction: SessionReconstruction | undefined): number {
  const turnsCompleted = reconstruction?.session?.turns_completed
  if (typeof turnsCompleted === 'number') return turnsCompleted

  return Math.max(
    0,
    ...(reconstruction?.events ?? []).map((event) =>
      typeof event.turn_index === 'number' ? event.turn_index : 0,
    ),
  )
}

function shuffleMessages(messages: string[]): string[] {
  const shuffled = [...messages]
  for (let i = shuffled.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1))
    const current = shuffled[i]
    shuffled[i] = shuffled[j]
    shuffled[j] = current
  }
  return shuffled
}

function PlayPage() {
  const { sessionId } = useParams({ from: '/play/$sessionId' })
  const { gameName, runName } = useSearch({ from: '/play/$sessionId' })
  const navigate = useNavigate()
  const { data: reconstruction, isLoading: reconstructionLoading } = useQuery({
    queryKey: ['session-reconstruction', sessionId],
    queryFn: () => httpClient<SessionReconstruction>(`/api/sessions/${sessionId}/reconstruction`),
    retry: false,
  })
  const terminalReconstruction = isTerminalSessionStatus(reconstruction?.session?.status)
  const shouldConnectWebSocket = !reconstructionLoading && !terminalReconstruction
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
  } = useSessionWebSocket(sessionId, { enabled: shouldConnectWebSocket })

  const [input, setInput] = useState('')
  const [feedbackPendingEventId, setFeedbackPendingEventId] = useState<string | null>(null)
  const [selectedCommandIndex, setSelectedCommandIndex] = useState(0)
  const [thinkingMessageIndex, setThinkingMessageIndex] = useState(0)
  const [longThinking, setLongThinking] = useState(false)
  const [thinkingMessageQueue, setThinkingMessageQueue] = useState(() =>
    shuffleMessages(THINKING_MESSAGES),
  )
  const [longThinkingMessageQueue, setLongThinkingMessageQueue] = useState(() =>
    shuffleMessages(LONG_THINKING_MESSAGES),
  )
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
  }, [messages, reconstruction, waiting])

  useEffect(() => {
    setThinkingMessageIndex(0)
    setLongThinking(false)
    if (!waiting) return

    setThinkingMessageQueue(shuffleMessages(THINKING_MESSAGES))
    setLongThinkingMessageQueue(shuffleMessages(LONG_THINKING_MESSAGES))

    const intervalId = window.setInterval(() => {
      setThinkingMessageIndex((current) => current + 1)
    }, THINKING_MESSAGE_INTERVAL_MS)
    const longThinkingTimeoutId = window.setTimeout(() => {
      setThinkingMessageIndex(0)
      setLongThinkingMessageQueue(shuffleMessages(LONG_THINKING_MESSAGES))
      setLongThinking(true)
    }, LONG_THINKING_MESSAGE_DELAY_MS)

    return () => {
      window.clearInterval(intervalId)
      window.clearTimeout(longThinkingTimeoutId)
    }
  }, [waiting])

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

  const readOnlyMessages = useMemo(
    () => messagesFromReconstruction(reconstruction),
    [reconstruction],
  )
  const displayMessages = terminalReconstruction ? readOnlyMessages : messages
  const displayTurns = terminalReconstruction ? turnsFromReconstruction(reconstruction) : turns
  const displayExited = terminalReconstruction || exited
  const displayPcHid = terminalReconstruction ? (reconstruction?.session?.pc_hid ?? null) : pcHid
  const displayNpcHid = terminalReconstruction ? (reconstruction?.session?.npc_hid ?? null) : npcHid

  const isConnecting =
    !terminalReconstruction &&
    (reconstructionLoading || wsState === 'connecting' || wsState === 'auth')
  const isError = wsState === 'error'
  const isClosed = terminalReconstruction || wsState === 'closed' || exited
  // Allow drafting at all times except terminal states (closed/error).
  const inputDisabled = isClosed || isError
  const gameReady = shouldConnectWebSocket && wsState === 'ready' && turns > 0 && !isReplaying
  const canSubmitTurn = gameReady && !waiting && !displayExited && !inputDisabled && !!input.trim()

  function submitInput() {
    const text = input.trim()
    if (!canSubmitTurn) return
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
        canSubmitTurn && selectedSuggestion && typedCommand !== selectedSuggestion.command

      if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey && canAutocompleteWithEnter)) {
        e.preventDefault()
        if (selectedSuggestion) {
          applyCommandSuggestion(selectedSuggestion)
        }
        return
      }
    }

    // Enter alone submits; Shift+Enter inserts a newline.
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (canSubmitTurn) {
        submitInput()
      }
    }
  }

  async function handleClose() {
    if (runName) {
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

  const sendDisabled = !canSubmitTurn
  const thinkingMessages = longThinking ? longThinkingMessageQueue : thinkingMessageQueue
  const thinkingMessage =
    thinkingMessages[thinkingMessageIndex % thinkingMessages.length] ?? THINKING_MESSAGES[0]

  return (
    <div className="h-screen flex flex-col bg-background">
      <header className="border-b px-4 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="font-semibold text-sm">{gameName || 'Game'}</h1>
          <Badge variant="outline" className="text-xs">
            Turn {displayTurns}
          </Badge>
          {displayPcHid && (
            <Badge variant="secondary" className="text-xs" title="Your character">
              Player Character: {displayPcHid}
            </Badge>
          )}
          {displayNpcHid && (
            <Badge variant="secondary" className="text-xs" title="Simulator character">
              Simulator Character: {displayNpcHid}
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
          {(isConnecting || (!terminalReconstruction && turns === 0 && wsState === 'ready')) && (
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

          {displayMessages.map((msg) => (
            <ChatMessageBubble
              key={msg.id}
              message={msg}
              feedbackPending={!!msg.eventId && feedbackPendingEventId === msg.eventId}
              onSubmitFeedback={handleSubmitFeedback}
              onClearFeedback={handleClearFeedback}
            />
          ))}

          {/* Animated "thinking" indicator shown while waiting for the AI response */}
          {waiting && (
            <div className="flex justify-start">
              <output
                className="inline-flex max-w-[min(82vw,32rem)] items-center gap-2.5 rounded-2xl rounded-bl-sm bg-muted/85 px-3.5 py-2.5 text-muted-foreground shadow-sm"
                aria-live="polite"
              >
                <span
                  className="relative flex h-4 w-4 shrink-0 items-center justify-center"
                  aria-hidden="true"
                >
                  <span className="absolute h-4 w-4 rounded-full border border-muted-foreground/20" />
                  <span className="h-2 w-2 rounded-full bg-muted-foreground/70 animate-pulse" />
                </span>
                <span className="text-sm leading-5">{thinkingMessage}</span>
                <span className="flex shrink-0 items-center gap-1 pl-0.5" aria-hidden="true">
                  <span className="h-1 w-1 rounded-full bg-muted-foreground/70 animate-bounce [animation-delay:0ms]" />
                  <span className="h-1 w-1 rounded-full bg-muted-foreground/70 animate-bounce [animation-delay:150ms]" />
                  <span className="h-1 w-1 rounded-full bg-muted-foreground/70 animate-bounce [animation-delay:300ms]" />
                </span>
              </output>
            </div>
          )}

          {displayExited && (
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
    runName: typeof search.runName === 'string' ? search.runName : '',
  }),
  beforeLoad: async () => {
    const serverConfig = await getServerConfig()
    if (serverConfig.authentication_required) {
      await requireAuth()
      return
    }
    await ensureAnonymousAuth()
  },
  component: PlayPage,
})
