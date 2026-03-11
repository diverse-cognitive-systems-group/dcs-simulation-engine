// Renders a single chat message bubble. User messages align right; AI messages
// align left with visual styling that varies by event type (normal, info, error, warning).

import ReactMarkdown from 'react-markdown'
import type { ChatMessage, EventType } from '@/hooks/use-session-websocket'
import { cn } from '@/lib/utils'

// Maps each server event type to Tailwind classes. An empty string means the default
// muted bubble style (applied in the JSX below) is used instead.
const EVENT_STYLES: Record<EventType, string> = {
  ai: '',
  info: 'opacity-70',
  error: 'bg-destructive/10 border border-destructive/30 text-destructive rounded-md px-3 py-2',
  warning: 'bg-yellow-50 border border-yellow-300 text-yellow-900 rounded-md px-3 py-2',
}

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

interface ChatMessageProps {
  message: ChatMessage
}

export function ChatMessageBubble({ message }: ChatMessageProps) {
  const isUser = message.role === 'user'
  const eventType = message.eventType ?? 'ai'
  const time = formatTime(message.timestamp)

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

  return (
    <div className="flex flex-col items-start gap-0.5">
      {/* If the event type has no override style, fall back to the default muted bubble. */}
      <div
        className={cn(
          'max-w-[min(82vw,76ch)] text-sm',
          style || 'bg-muted rounded-2xl rounded-bl-sm px-4 py-2',
        )}
      >
        {(eventType === 'error' || eventType === 'warning') && (
          <p className="font-semibold text-xs uppercase tracking-wide mb-1">
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
      <span className="text-[10px] text-muted-foreground pl-1">{time}</span>
    </div>
  )
}
