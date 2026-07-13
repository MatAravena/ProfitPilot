import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { TradingWebSocket, HEARTBEAT_INTERVAL, PONG_TIMEOUT } from './websocket'

/**
 * Controllable WebSocket double. Records every instance created so tests can
 * assert how many sockets the client opened, and lets tests drive open/close.
 */
class MockWebSocket {
  static instances: MockWebSocket[] = []
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  readyState = MockWebSocket.CONNECTING
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  onmessage: ((e: MessageEvent) => void) | null = null
  url: string
  send = vi.fn()

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  close() {
    if (this.readyState === MockWebSocket.CLOSED) return
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.()
  }

  simulateOpen() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.()
  }

  simulateMessage(channel: string, data: unknown = {}) {
    this.onmessage?.({ data: JSON.stringify({ channel, data }) } as MessageEvent)
  }
}

describe('TradingWebSocket', () => {
  let originalWS: typeof WebSocket

  beforeEach(() => {
    vi.useFakeTimers()
    MockWebSocket.instances = []
    originalWS = globalThis.WebSocket
    // @ts-expect-error installing a test double
    globalThis.WebSocket = MockWebSocket
  })

  afterEach(() => {
    globalThis.WebSocket = originalWS
    // Drop any still-pending fake timers (reconnect/heartbeat) BEFORE switching
    // back to real timers, so nothing leaks into the next test in the full run.
    vi.clearAllTimers()
    vi.useRealTimers()
  })

  it('does not reconnect after an intentional disconnect', () => {
    const client = new TradingWebSocket()
    client.connect()
    MockWebSocket.instances[0].simulateOpen()

    client.disconnect()
    vi.advanceTimersByTime(60_000)

    // Deliberate close must not schedule a reconnect.
    expect(MockWebSocket.instances).toHaveLength(1)
  })

  it('does not open a second socket when one is already active', () => {
    const client = new TradingWebSocket()
    client.connect()
    MockWebSocket.instances[0].simulateOpen()

    client.connect() // e.g. StrictMode re-mount / HMR re-invoking the effect

    expect(MockWebSocket.instances).toHaveLength(1)
    client.disconnect()
  })

  it('reconnects exactly once after an unexpected server-side close', () => {
    const client = new TradingWebSocket()
    client.connect()
    MockWebSocket.instances[0].simulateOpen()

    MockWebSocket.instances[0].close() // server drops the connection
    vi.advanceTimersByTime(1_000)

    expect(MockWebSocket.instances).toHaveLength(2)
    client.disconnect()
  })

  it('sends a heartbeat ping once connected', () => {
    const client = new TradingWebSocket()
    client.connect()
    const socket = MockWebSocket.instances[0]
    socket.simulateOpen()

    vi.advanceTimersByTime(HEARTBEAT_INTERVAL)

    expect(socket.send).toHaveBeenCalledWith(JSON.stringify({ type: 'ping' }))
    client.disconnect()
  })

  it('tears down and reconnects when a pong is not received in time', () => {
    const client = new TradingWebSocket()
    client.connect()
    MockWebSocket.instances[0].simulateOpen()

    // Heartbeat fires, no pong arrives within the timeout → connection is dead.
    vi.advanceTimersByTime(HEARTBEAT_INTERVAL + PONG_TIMEOUT)
    expect(MockWebSocket.instances[0].readyState).toBe(MockWebSocket.CLOSED)

    // …and the dead socket triggers the normal reconnect path.
    vi.advanceTimersByTime(1_000)
    expect(MockWebSocket.instances).toHaveLength(2)
    client.disconnect()
  })

  it('stays connected when pongs arrive', () => {
    const client = new TradingWebSocket()
    client.connect()
    const socket = MockWebSocket.instances[0]
    socket.simulateOpen()

    // Ping goes out, server answers with a pong before the watchdog fires.
    vi.advanceTimersByTime(HEARTBEAT_INTERVAL)
    socket.simulateMessage('pong')
    vi.advanceTimersByTime(PONG_TIMEOUT)

    expect(socket.readyState).toBe(MockWebSocket.OPEN)
    expect(MockWebSocket.instances).toHaveLength(1)
    client.disconnect()
  })
})
