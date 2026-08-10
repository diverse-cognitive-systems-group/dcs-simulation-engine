import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useSessionWebSocket } from '@/hooks/use-session-websocket'
import { setAuth } from '@/lib/auth'
import { getLatestMockWebSocket } from './helpers/mock-websocket'

function renderSessionHook(sessionId = 'sess-1', options: { enabled?: boolean } = {}) {
  return renderHook(() => useSessionWebSocket(sessionId, options))
}

describe('useSessionWebSocket', () => {
  it('transitions connecting → auth → ready on successful handshake', async () => {
    setAuth('dev-key', 'player-1', 'Test Player')
    const { result } = renderSessionHook()

    expect(result.current.wsState).toBe('connecting')

    await waitFor(() => {
      expect(result.current.wsState).toBe('auth')
    })

    const socket = getLatestMockWebSocket()
    expect(socket).toBeDefined()
    expect(socket?.sent).toEqual([JSON.stringify({ type: 'auth', api_key: 'dev-key' })])

    act(() => {
      socket?.receive({ type: 'session_meta', pc_hid: 'pc-1', npc_hid: 'npc-1' })
    })

    expect(result.current.wsState).toBe('ready')
    expect(result.current.pcHid).toBe('pc-1')
    expect(result.current.npcHid).toBe('npc-1')
  })

  it('sets waiting on sendTurn and clears it on turn_end', async () => {
    setAuth('dev-key', 'player-1', 'Test Player')
    const { result } = renderSessionHook()

    await waitFor(() => {
      expect(result.current.wsState).toBe('auth')
    })

    const socket = getLatestMockWebSocket()
    act(() => {
      socket?.receive({ type: 'session_meta' })
      socket?.receive({ type: 'turn_end', turns: 1 })
    })

    await waitFor(() => {
      expect(result.current.turns).toBe(1)
    })

    act(() => {
      result.current.sendTurn('hello world')
    })

    expect(result.current.waiting).toBe(true)
    expect(socket?.sent.at(-1)).toBe(JSON.stringify({ type: 'advance', text: 'hello world' }))

    act(() => {
      socket?.receive({ type: 'turn_end', turns: 2 })
    })

    expect(result.current.waiting).toBe(false)
    expect(result.current.turns).toBe(2)
  })

  it('tracks replay lifecycle and blocks turns until replay_end', async () => {
    setAuth('dev-key', 'player-1', 'Test Player')
    const { result } = renderSessionHook()

    await waitFor(() => {
      expect(result.current.wsState).toBe('auth')
    })

    const socket = getLatestMockWebSocket()
    act(() => {
      socket?.receive({ type: 'replay_start' })
    })

    expect(result.current.isReplaying).toBe(true)

    act(() => {
      socket?.receive({
        type: 'replay_event',
        role: 'ai',
        event_type: 'info',
        content: 'Previously on...',
      })
      socket?.receive({ type: 'replay_end', turns: 3 })
    })

    expect(result.current.isReplaying).toBe(false)
    expect(result.current.turns).toBe(3)
    expect(result.current.messages).toHaveLength(1)
  })

  it('marks exited when turn_end includes exited: true', async () => {
    setAuth('dev-key', 'player-1', 'Test Player')
    const { result } = renderSessionHook()

    await waitFor(() => {
      expect(result.current.wsState).toBe('auth')
    })

    const socket = getLatestMockWebSocket()
    act(() => {
      socket?.receive({
        type: 'turn_end',
        turns: 5,
        exited: true,
        exit_reason: 'player_quit',
      })
    })

    expect(result.current.exited).toBe(true)
    expect(result.current.exitReason).toBe('player_quit')
  })

  it('closes on structured error frames and records failure details', async () => {
    setAuth('dev-key', 'player-1', 'Test Player')
    const { result } = renderSessionHook()

    await waitFor(() => {
      expect(result.current.wsState).toBe('auth')
    })

    const socket = getLatestMockWebSocket()
    act(() => {
      socket?.receive({
        type: 'error',
        failure_type: 'session_not_found',
        detail: 'Session is gone',
      })
    })

    expect(result.current.wsState).toBe('closed')
    expect(result.current.exited).toBe(true)
    expect(result.current.exitReason).toBe('session_not_found')
    expect(result.current.messages.at(-1)?.content).toBe('Session is gone')
    expect(result.current.waiting).toBe(false)
  })

  it('enters error state for unstructured error frames', async () => {
    setAuth('dev-key', 'player-1', 'Test Player')
    const { result } = renderSessionHook()

    await waitFor(() => {
      expect(result.current.wsState).toBe('auth')
    })

    const socket = getLatestMockWebSocket()
    act(() => {
      socket?.receive({ type: 'error', detail: 'Transient failure' })
    })

    expect(result.current.wsState).toBe('error')
    expect(result.current.exited).toBe(false)
  })

  it('does not open a socket when enabled is false', async () => {
    const { result } = renderSessionHook('sess-disabled', { enabled: false })

    await waitFor(() => {
      expect(result.current.wsState).toBe('closed')
    })

    expect(getLatestMockWebSocket()).toBeUndefined()
    expect(result.current.waiting).toBe(false)
  })
})
