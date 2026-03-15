// Renders a single chat message bubble. User messages align right; AI messages
// align left with visual styling that varies by event type (normal, info, error, warning).

import { ThumbsDown, ThumbsUp } from 'lucide-react'
import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import type { ChatMessage, EventType, MessageFeedback } from '@/hooks/use-session-websocket'
import { cn } from '@/lib/utils'

// Maps each server event type to Tailwind classes. An empty string means the default
// muted bubble style (applied in the JSX below) is used instead.
const EVENT_STYLES: Record<EventType, string> = {
  ai: '',
  info: 'opacity-85',
  error: 'bg-destructive/10 border border-destructive/30 text-destructive rounded-md px-3 py-2',
  warning: 'bg-yellow-50 border border-yellow-300 text-yellow-900 rounded-md px-3 py-2',
}

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

interface ChatMessageProps {
  message: ChatMessage
  feedbackPending?: boolean
  onSubmitFeedback?: (payload: {
    eventId: string
    liked: boolean
    comment: string
  }) => Promise<MessageFeedback | undefined>
  onClearFeedback?: (eventId: string) => Promise<void>
}

export function ChatMessageBubble({
  message,
  feedbackPending = false,
  onSubmitFeedback,
  onClearFeedback,
}: ChatMessageProps) {
  const isUser = message.role === 'user'
  const eventType = message.eventType ?? 'ai'
  const time = formatTime(message.timestamp)
  const savedFeedback = message.feedback
  const canFeedback = !isUser && eventType === 'ai' && typeof message.eventId === 'string'
  const [confirmedFeedback, setConfirmedFeedback] = useState<MessageFeedback | undefined>(
    savedFeedback,
  )
  const [composerOpen, setComposerOpen] = useState(false)
  const [draftLiked, setDraftLiked] = useState<boolean | null>(savedFeedback?.liked ?? null)
  const [draftComment, setDraftComment] = useState(savedFeedback?.comment ?? '')
  const [feedbackError, setFeedbackError] = useState<string | null>(null)

  useEffect(() => {
    setConfirmedFeedback(savedFeedback)
  }, [savedFeedback])

  useEffect(() => {
    if (composerOpen) return
    setDraftLiked(confirmedFeedback?.liked ?? null)
    setDraftComment(confirmedFeedback?.comment ?? '')
    setFeedbackError(null)
  }, [confirmedFeedback, composerOpen])

  if (isUser) {
    return (
      <div className="flex flex-col items-end gap-0.5">
        <div className="max-w-[min(78vw,70ch)] rounded-2xl rounded-br-sm border border-primary/35 bg-primary text-primary-foreground px-4 py-2 text-sm shadow-sm">
          {/* User messages are plain text — no markdown needed. */}
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>
        <span className="text-[10px] text-muted-foreground pr-1">{time}</span>
      </div>
    )
  }

  const style = EVENT_STYLES[eventType]
  const activeLiked = composerOpen ? draftLiked : (confirmedFeedback?.liked ?? null)

  async function handleReactionClick(liked: boolean) {
    if (!message.eventId || feedbackPending) return

    if (confirmedFeedback && confirmedFeedback.liked === liked && onClearFeedback) {
      try {
        setFeedbackError(null)
        await onClearFeedback(message.eventId)
        setConfirmedFeedback(undefined)
        setDraftLiked(null)
        setDraftComment('')
        setComposerOpen(false)
      } catch (error) {
        setFeedbackError(error instanceof Error ? error.message : 'Failed to clear feedback.')
      }
      return
    }

    setDraftLiked(liked)
    setDraftComment((prev) => {
      if (composerOpen) return prev
      return confirmedFeedback?.comment ?? ''
    })
    setComposerOpen(true)
    setFeedbackError(null)
  }

  function cancelComposer() {
    setComposerOpen(false)
    setDraftLiked(confirmedFeedback?.liked ?? null)
    setDraftComment(confirmedFeedback?.comment ?? '')
    setFeedbackError(null)
  }

  async function handleFeedbackSubmit() {
    if (!message.eventId || draftLiked === null || !onSubmitFeedback || feedbackPending) return

    const comment = draftComment.trim()
    if (!comment) {
      setFeedbackError('Feedback comment is required.')
      return
    }

    try {
      setFeedbackError(null)
      const submittedFeedback = await onSubmitFeedback({
        eventId: message.eventId,
        liked: draftLiked,
        comment,
      })
      setConfirmedFeedback(
        submittedFeedback ?? {
          liked: draftLiked,
          comment,
          submittedAt: new Date().toISOString(),
        },
      )
      setDraftComment(comment)
      setComposerOpen(false)
    } catch (error) {
      setFeedbackError(error instanceof Error ? error.message : 'Failed to save feedback.')
    }
  }

  return (
    <div className="flex flex-col items-start gap-0.5">
      <div className="w-full max-w-[min(82vw,76ch)]">
        {/* If the event type has no override style, fall back to the default muted bubble. */}
        <div className={cn('text-sm', style || 'bg-muted rounded-2xl rounded-bl-sm px-4 py-2')}>
          {(eventType === 'error' || eventType === 'warning') && (
            <p className="mb-1 font-semibold text-xs uppercase tracking-wide">
              {eventType === 'error' ? 'Error' : 'Warning'}
            </p>
          )}
          {/*
            ReactMarkdown converts markdown syntax to HTML elements.
            The `prose` Tailwind class (from @tailwindcss/typography) styles headings,
            paragraphs, lists, code blocks, etc. consistently.
            `prose-sm` keeps the font size small to match the chat context.
          */}
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
        </div>
        <div className="flex flex-col items-start gap-2">
          <span className="pl-1 text-[10px] text-muted-foreground">{time}</span>
          {canFeedback && (
            <div className="flex w-full flex-col items-start gap-2">
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="icon-xs"
                  disabled={feedbackPending}
                  className={cn(
                    'border-border/70 text-muted-foreground transition-colors',
                    activeLiked === true
                      ? '!border-emerald-600 !bg-emerald-600 !text-white hover:!border-emerald-600 hover:!bg-emerald-600/90 hover:!text-white'
                      : 'hover:border-emerald-300 hover:bg-emerald-100 hover:text-emerald-700',
                  )}
                  aria-label="Like assistant message"
                  onClick={() => void handleReactionClick(true)}
                >
                  <ThumbsUp />
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="icon-xs"
                  disabled={feedbackPending}
                  className={cn(
                    'border-border/70 text-muted-foreground transition-colors',
                    activeLiked === false
                      ? '!border-rose-600 !bg-rose-600 !text-white hover:!border-rose-600 hover:!bg-rose-600/90 hover:!text-white'
                      : 'hover:border-rose-300 hover:bg-rose-100 hover:text-rose-700',
                  )}
                  aria-label="Dislike assistant message"
                  onClick={() => void handleReactionClick(false)}
                >
                  <ThumbsDown />
                </Button>
              </div>

              {composerOpen && (
                <div className="w-full rounded-xl border border-border/80 bg-background/95 p-3 shadow-sm">
                  <div className="space-y-2">
                    <Textarea
                      value={draftComment}
                      onChange={(e) => setDraftComment(e.target.value)}
                      placeholder="Describe your feedback"
                      rows={3}
                      disabled={feedbackPending}
                      className="min-h-24 w-full bg-background"
                    />
                    {feedbackError && <p className="text-xs text-destructive">{feedbackError}</p>}
                    <div className="flex items-center gap-2">
                      <Button
                        type="button"
                        size="sm"
                        disabled={feedbackPending || !draftComment.trim()}
                        onClick={handleFeedbackSubmit}
                      >
                        {feedbackPending ? 'Submitting...' : 'Submit'}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={feedbackPending}
                        onClick={cancelComposer}
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
