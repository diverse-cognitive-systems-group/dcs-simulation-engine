import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'
import { MockWebSocket, resetMockWebSockets } from './helpers/mock-websocket'

vi.stubGlobal('WebSocket', MockWebSocket)

afterEach(() => {
  resetMockWebSockets()
  sessionStorage.clear()
})
