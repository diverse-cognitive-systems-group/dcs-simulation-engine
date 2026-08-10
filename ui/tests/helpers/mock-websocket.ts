type WsHandler = ((event: Event) => void) | null

const instances: MockWebSocket[] = []

export function resetMockWebSockets(): void {
  instances.length = 0
}

export function getLatestMockWebSocket(): MockWebSocket | undefined {
  return instances.at(-1)
}

export class MockWebSocket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3

  readonly url: string
  readyState = MockWebSocket.CONNECTING

  onopen: WsHandler = null
  onmessage: WsHandler = null
  onerror: WsHandler = null
  onclose: WsHandler = null

  sent: string[] = []

  constructor(url: string) {
    this.url = url
    instances.push(this)
    queueMicrotask(() => {
      if (this.readyState !== MockWebSocket.CONNECTING) return
      this.readyState = MockWebSocket.OPEN
      this.onopen?.(new Event('open'))
    })
  }

  send(data: string): void {
    this.sent.push(data)
  }

  close(): void {
    if (this.readyState === MockWebSocket.CLOSED) return
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.(new CloseEvent('close'))
  }

  receive(data: unknown): void {
    if (this.readyState !== MockWebSocket.OPEN) return
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent)
  }

  triggerError(): void {
    this.onerror?.(new Event('error'))
  }
}
