// Custom hook that manages the WebSocket connection for a live game session.
// Handles the auth handshake, maps incoming server frames to typed chat messages,
// and exposes sendTurn/closeSession callbacks to the play page.

import { useCallback, useEffect, useRef, useState } from 'react'
import { getApiKey } from '../lib/auth'

export type EventType = 'ai' | 'info' | 'error' | 'warning'

export interface MessageFeedback {
  liked: boolean
  comment: string
  submittedAt: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'ai'
  eventType?: EventType
  content: string
  eventId?: string
  feedback?: MessageFeedback
  // Unix timestamp (ms) set when the message is added to the list.
  timestamp: number
}

type WsState = 'connecting' | 'auth' | 'ready' | 'closed' | 'error'

export function useSessionWebSocket(sessionId: string) {
  // useState holds reactive values that cause the component to re-render when they change.
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [wsState, setWsState] = useState<WsState>('connecting')
  const [turns, setTurns] = useState(0)
  const [exited, setExited] = useState(false)
  // waiting is true between sendTurn() and the server's turn_end frame.
  const [waiting, setWaiting] = useState(false)
  // useRef holds a mutable value that does NOT trigger re-renders — used for the socket
  // instance and the message counter so we can access them inside callbacks without
  // needing them as effect dependencies.
  const ws = useRef<WebSocket | null>(null)
  const msgCounter = useRef(0)

  const nextId = () => {
    msgCounter.current += 1
    return String(msgCounter.current)
  }

  // useEffect runs after the component mounts (and again if sessionId changes).
  // The returned cleanup function closes the socket when the component unmounts,
  // preventing dangling connections if the user navigates away.
  //
  // IMPORTANT: React 18 StrictMode intentionally mounts → unmounts → remounts every
  // component in development to surface side-effect bugs. We use a `cancelled` flag so
  // callbacks from the first (cancelled) mount don't update state after the second mount
  // takes over. We also only close sockets that are still CONNECTING or OPEN.
  // biome-ignore lint/correctness/useExhaustiveDependencies: intentional — only re-connect on sessionId change
  useEffect(() => {
    let cancelled = false

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const socket = new WebSocket(`${proto}//${window.location.host}/api/play/game/${sessionId}/ws`)
    ws.current = socket
    setWsState('connecting')

    socket.onopen = () => {
      if (cancelled) return
      // The server requires an auth frame before it will send any game events.
      const apiKey = getApiKey()
      if (apiKey) {
        socket.send(JSON.stringify({ type: 'auth', api_key: apiKey }))
        setWsState('auth')
      }
    }

    socket.onmessage = (ev) => {
      if (cancelled) return
      const frame = JSON.parse(ev.data as string)

      if (frame.type === 'error') {
        setWsState('error')
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: 'ai',
            eventType: 'error',
            content: frame.detail,
            timestamp: Date.now(),
          },
        ])
        setWaiting(false)
        return
      }

      // Any non-error frame after auth means authentication succeeded.
      setWsState('ready')

      if (frame.type === 'event') {
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: 'ai',
            eventType: frame.event_type as EventType,
            content: frame.content,
            eventId: typeof frame.event_id === 'string' ? frame.event_id : undefined,
            timestamp: Date.now(),
          },
        ])
        setWaiting(false)
      }

      if (frame.type === 'turn_end') {
        setTurns(frame.turns as number)
        setWaiting(false)
        if (frame.exited) setExited(true)
      }

      if (frame.type === 'closed') {
        setWsState('closed')
        setWaiting(false)
        socket.close()
      }
    }

    socket.onerror = () => {
      if (cancelled) return
      setWsState('error')
      setWaiting(false)
    }

    socket.onclose = () => {
      if (cancelled) return
      setWsState((prev) => (prev !== 'closed' ? 'closed' : prev))
    }

    return () => {
      // Mark this effect instance as cancelled so stale callbacks are ignored.
      cancelled = true
      // Only close sockets that haven't already finished closing.
      if (socket.readyState === WebSocket.CONNECTING || socket.readyState === WebSocket.OPEN) {
        socket.close()
      }
    }
  }, [sessionId])

  // useCallback memoizes the function so its reference stays stable across renders,
  // which matters here because sendTurn is used in JSX event handlers.
  // biome-ignore lint/correctness/useExhaustiveDependencies: ws.current is a ref — stable by definition
  const sendTurn = useCallback((text: string) => {
    if (ws.current?.readyState !== WebSocket.OPEN) return
    setMessages((prev) => [
      ...prev,
      { id: nextId(), role: 'user', content: text, timestamp: Date.now() },
    ])
    setWaiting(true)
    ws.current.send(JSON.stringify({ type: 'advance', text }))
  }, [])

  const closeSession = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ type: 'close' }))
    }
  }, [])

  const setMessageFeedback = useCallback(
    (eventId: string, feedback: MessageFeedback | undefined) => {
      setMessages((prev) =>
        prev.map((message) => (message.eventId === eventId ? { ...message, feedback } : message)),
      )
    },
    [],
  )

  return { messages, wsState, turns, exited, waiting, sendTurn, closeSession, setMessageFeedback }
}
