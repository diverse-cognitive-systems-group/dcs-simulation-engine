// Live play page at /play/:sessionId. Connects to the game session via WebSocket,
// renders the chat transcript, and lets the player submit turns.

import { createRoute, useNavigate, useParams, useSearch } from '@tanstack/react-router'
import { useEffect, useRef, useState } from 'react'
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
import { requireAuth, rootRoute } from '../__root'

// TODO: We should probably have a shared config file for both server and UI
const MAX_INPUT_LENGTH = 350

function PlayPage() {
  const { sessionId } = useParams({ from: '/play/$sessionId' })
  const { gameName } = useSearch({ from: '/play/$sessionId' })
  const navigate = useNavigate()
  // useSessionWebSocket opens the WebSocket connection and returns reactive state plus
  // action callbacks; see hooks/use-session-websocket.ts for the protocol details.
  const { messages, wsState, turns, exited, waiting, sendTurn, closeSession, setMessageFeedback } =
    useSessionWebSocket(sessionId)

  const [input, setInput] = useState('')
  const [feedbackPendingEventId, setFeedbackPendingEventId] = useState<string | null>(null)
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

  function submitInput() {
    const text = input.trim()
    if (!text || exited || wsState !== 'ready' || waiting) return
    sendTurn(text)
    setInput('')
  }

  function handleSubmit(e: React.SubmitEvent) {
    e.preventDefault()
    submitInput()
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Enter alone submits; Shift+Enter inserts a newline.
    const canSubmit = !waiting && !exited && wsState === 'ready' && !!input.trim()
    if (e.key === 'Enter' && !e.shiftKey && canSubmit) {
      e.preventDefault()
      submitInput()
    }
  }

  async function handleClose() {
    closeSession()
    await navigate({ to: '/games' })
  }

  async function handleSubmitFeedback(payload: {
    eventId: string
    liked: boolean
    comment: string
  }): Promise<MessageFeedback> {
    setFeedbackPendingEventId(payload.eventId)

    try {
      const response = await submitMessageFeedback({
        sessionId,
        eventId: payload.eventId,
        data: {
          liked: payload.liked,
          comment: payload.comment,
        },
      })
      const result = unwrapOrvalData<SubmitSessionEventFeedbackResponse>(response)
      if (!result?.feedback) {
        throw new Error('Feedback save did not return stored feedback.')
      }

      const feedback: MessageFeedback = {
        liked: result.feedback.liked,
        comment: result.feedback.comment,
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
  // Send is blocked while waiting so users can draft the next turn without double-submitting.
  const sendDisabled = !input.trim() || inputDisabled || waiting

  return (
    <div className="h-screen flex flex-col bg-background">
      <header className="border-b px-4 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <h1 className="font-semibold text-sm">{gameName || 'Game'}</h1>
          <Badge variant="outline" className="text-xs">
            Turn {turns}
          </Badge>
          {isClosed && (
            <Badge variant="secondary" className="text-xs">
              Ended
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Button variant="outline" size="sm" onClick={handleClose}>
            Close Session
          </Button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        <div className="mx-auto w-full max-w-[96vw] sm:max-w-[92vw] lg:max-w-[86vw] xl:max-w-[80vw] space-y-3">
          {isConnecting && (
            <div className="flex flex-col items-center gap-3 py-8 text-muted-foreground">
              {/* CSS-only spinner: a bordered circle with one colored arc, rotated by animation */}
              <div className="w-6 h-6 rounded-full border-2 border-muted border-t-foreground animate-spin" />
              <p className="text-sm italic">Loading simulation environment…</p>
            </div>
          )}

          {isError && (
            <FatalErrorOverlay
              message="Connection error. Please close and try again."
              onReturn={handleClose}
            />
          )}

          {messages.map((msg) => (
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
              <div className="bg-muted rounded-2xl rounded-bl-sm px-4 py-3 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:0ms]" />
                <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:150ms]" />
                <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:300ms]" />
              </div>
            </div>
          )}

          {exited && (
            <div className="text-center py-4">
              <Badge variant="secondary">Simulation ended</Badge>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      <form onSubmit={handleSubmit} className="border-t px-4 py-3 flex gap-2 items-end shrink-0">
        <div className="flex-1 space-y-1">
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
  }),
  beforeLoad: requireAuth,
  component: PlayPage,
})
