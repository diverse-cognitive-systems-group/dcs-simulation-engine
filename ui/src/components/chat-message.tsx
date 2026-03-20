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
  info: 'rounded-2xl border border-border/70 bg-muted/40 px-4 py-3',
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
    doesntMakeSense: boolean
    outOfCharacter: boolean
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
  const canFeedback =
    !isUser &&
    eventType === 'ai' &&
    typeof message.eventId === 'string' &&
    !!onSubmitFeedback &&
    !!onClearFeedback
  const [confirmedFeedback, setConfirmedFeedback] = useState<MessageFeedback | undefined>(
    savedFeedback,
  )
  const [composerOpen, setComposerOpen] = useState(false)
  const [draftLiked, setDraftLiked] = useState<boolean | null>(savedFeedback?.liked ?? null)
  const [draftComment, setDraftComment] = useState(savedFeedback?.comment ?? '')
  const [draftDoesntMakeSense, setDraftDoesntMakeSense] = useState(
    savedFeedback?.doesntMakeSense ?? false,
  )
  const [draftOutOfCharacter, setDraftOutOfCharacter] = useState(
    savedFeedback?.outOfCharacter ?? false,
  )
  const [feedbackError, setFeedbackError] = useState<string | null>(null)

  useEffect(() => {
    setConfirmedFeedback(savedFeedback)
    if (composerOpen) return
    setDraftLiked(savedFeedback?.liked ?? null)
    setDraftComment(savedFeedback?.comment ?? '')
    setDraftDoesntMakeSense(savedFeedback?.doesntMakeSense ?? false)
    setDraftOutOfCharacter(savedFeedback?.outOfCharacter ?? false)
    setFeedbackError(null)
  }, [savedFeedback, composerOpen])

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
  const doesntMakeSense = confirmedFeedback?.doesntMakeSense ?? false
  const outOfCharacter = confirmedFeedback?.outOfCharacter ?? false
  const isInfo = eventType === 'info'
  const activeLiked = composerOpen ? draftLiked : (confirmedFeedback?.liked ?? null)

  function resetDraftFromConfirmed() {
    setDraftLiked(confirmedFeedback?.liked ?? null)
    setDraftComment(confirmedFeedback?.comment ?? '')
    setDraftDoesntMakeSense(confirmedFeedback?.doesntMakeSense ?? false)
    setDraftOutOfCharacter(confirmedFeedback?.outOfCharacter ?? false)
  }

  async function handleReactionClick(liked: boolean) {
    if (!message.eventId || feedbackPending) return

    if (confirmedFeedback && !composerOpen && confirmedFeedback.liked === liked && onClearFeedback) {
      try {
        setFeedbackError(null)
        await onClearFeedback(message.eventId)
        setConfirmedFeedback(undefined)
        setComposerOpen(false)
        setDraftLiked(null)
        setDraftComment('')
        setDraftDoesntMakeSense(false)
        setDraftOutOfCharacter(false)
        return
      } catch (error) {
        setFeedbackError(error instanceof Error ? error.message : 'Failed to clear feedback.')
      }
    }

    setDraftLiked(liked)
    if (!composerOpen) {
      setDraftComment(confirmedFeedback?.comment ?? '')
    }
    if (liked) {
      setDraftDoesntMakeSense(false)
      setDraftOutOfCharacter(false)
    } else if (!(composerOpen && draftLiked === false)) {
      setDraftDoesntMakeSense(confirmedFeedback?.liked === false ? doesntMakeSense : false)
      setDraftOutOfCharacter(confirmedFeedback?.liked === false ? outOfCharacter : false)
    }
    setComposerOpen(true)
    setFeedbackError(null)
  }

  function handleFeedbackToggle(flag: 'doesntMakeSense' | 'outOfCharacter') {
    if (feedbackPending || draftLiked !== false) return

    if (flag === 'doesntMakeSense') {
      setDraftDoesntMakeSense((current) => !current)
      return
    }
    setDraftOutOfCharacter((current) => !current)
  }

  function cancelComposer() {
    setComposerOpen(false)
    resetDraftFromConfirmed()
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
        doesntMakeSense: draftLiked ? false : draftDoesntMakeSense,
        outOfCharacter: draftLiked ? false : draftOutOfCharacter,
      })
      const nextFeedback =
        submittedFeedback ?? {
          liked: draftLiked,
          comment,
          doesntMakeSense: draftLiked ? false : draftDoesntMakeSense,
          outOfCharacter: draftLiked ? false : draftOutOfCharacter,
          submittedAt: new Date().toISOString(),
        }
      setConfirmedFeedback(nextFeedback)
      setDraftComment(comment)
      setComposerOpen(false)
    } catch (error) {
      setFeedbackError(error instanceof Error ? error.message : 'Failed to save feedback.')
    }
  }

  return (
    <div className={cn('flex flex-col gap-0.5', isInfo ? 'items-center' : 'items-start')}>
      <div className={cn('w-full', isInfo ? 'max-w-[min(76vw,72ch)]' : 'max-w-[min(82vw,76ch)]')}>
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
          <div className="prose prose-sm dark:prose-invert max-w-none [&_code]:rounded [&_code]:bg-muted/70 [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[0.95em] [&_code::before]:content-none [&_code::after]:content-none">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
        </div>
        <div className={cn('flex flex-col gap-2', isInfo ? 'items-center' : 'items-start')}>
          <span className={cn('text-[10px] text-muted-foreground', isInfo ? '' : 'pl-1')}>
            {time}
          </span>
          {canFeedback && (
            <div className="flex w-full flex-col items-start gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="icon-xs"
                  disabled={feedbackPending}
                  className={cn(
                    'border-border/70 text-muted-foreground transition-colors',
                    activeLiked === true
                      ? '!border-emerald-600 !bg-emerald-600 !text-white hover:!border-emerald-600 hover:!bg-emerald-600/90 hover:!text-white'
                      : 'hover:border-emerald-300 hover:bg-emerald-100 hover:text-emerald-800',
                  )}
                  aria-label="Like assistant message"
                  title="Like"
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
                  title="Dislike"
                  onClick={() => void handleReactionClick(false)}
                >
                  <ThumbsDown />
                </Button>
              </div>
              {composerOpen && (
                <div className="w-full rounded-xl border border-border/80 bg-background/95 p-3 shadow-sm">
                  <div className="space-y-3">
                    {draftLiked === false && (
                      <div className="flex flex-wrap items-center gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={feedbackPending}
                          className={cn(
                            'border-border/70 text-muted-foreground transition-colors',
                            draftDoesntMakeSense
                              ? '!border-amber-600 !bg-amber-600 !text-white hover:!border-amber-600 hover:!bg-amber-600/90 hover:!text-white'
                              : 'hover:border-amber-300 hover:bg-amber-100 hover:text-amber-800',
                          )}
                          aria-label="Flag assistant message as not making sense"
                          onClick={() => handleFeedbackToggle('doesntMakeSense')}
                        >
                          Doesn&apos;t make sense
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={feedbackPending}
                          className={cn(
                            'border-border/70 text-muted-foreground transition-colors',
                            draftOutOfCharacter
                              ? '!border-rose-600 !bg-rose-600 !text-white hover:!border-rose-600 hover:!bg-rose-600/90 hover:!text-white'
                              : 'hover:border-rose-300 hover:bg-rose-100 hover:text-rose-700',
                          )}
                          aria-label="Flag assistant message as out of character"
                          onClick={() => handleFeedbackToggle('outOfCharacter')}
                        >
                          Out of character
                        </Button>
                      </div>
                    )}
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
                        onClick={() => void handleFeedbackSubmit()}
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
