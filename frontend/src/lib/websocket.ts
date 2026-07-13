import { useWebSocketStore } from '@/stores/websocket'
import { usePortfolioStore } from '@/stores/portfolio'
import { useStrategyStore } from '@/stores/strategy'
import { useSignalsStore } from '@/stores/signals'
import type { WSMessage, SignalRecord } from '@/types'

const MAX_RECONNECT_DELAY = 30_000

// Heartbeat: send a ping on an interval and expect a pong back. If the pong
// doesn't arrive in time the connection is treated as dead (half-open) and torn
// down so the normal reconnect path can re-establish it.
export const HEARTBEAT_INTERVAL = 20_000
export const PONG_TIMEOUT = 10_000

export class TradingWebSocket {
  private ws: WebSocket | null = null
  private reconnectDelay = 1_000
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private shouldReconnect = false
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null
  private pongTimer: ReturnType<typeof setTimeout> | null = null
  private handlers = new Map<string, Set<(data: unknown) => void>>()

  connect() {
    // Guard against overlapping sockets: a StrictMode re-mount or HMR update can
    // re-invoke this while a socket is already opening/open. Opening another one
    // leaks the previous connection and causes reconnect churn.
    if (
      this.ws &&
      (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)
    ) {
      return
    }

    this.shouldReconnect = true
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }

    const { setStatus } = useWebSocketStore.getState()
    setStatus('connecting')

    // Bind handlers to this specific socket so a stale one that closes later
    // can't mutate shared state after it has been replaced.
    const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`)
    this.ws = socket

    socket.onopen = () => {
      if (this.ws !== socket) return
      setStatus('connected')
      this.reconnectDelay = 1_000
      this.startHeartbeat(socket)
      const { subscribedSymbols } = useWebSocketStore.getState()
      subscribedSymbols.forEach((s) => this.subscribe(s))
    }

    socket.onmessage = (event: MessageEvent) => {
      try {
        const msg = JSON.parse(event.data as string) as WSMessage
        if (msg.channel === 'pong') {
          // Heartbeat acknowledged — the connection is alive.
          if (this.pongTimer) {
            clearTimeout(this.pongTimer)
            this.pongTimer = null
          }
          return
        }
        this.dispatch(msg.channel, msg.data)
        this.routeToStore(msg)
      } catch {
        // malformed frame — ignore
      }
    }

    socket.onclose = () => {
      if (this.ws !== socket) return // superseded socket — ignore
      this.stopHeartbeat()
      this.ws = null
      setStatus('disconnected')
      if (this.shouldReconnect) this.scheduleReconnect()
    }

    socket.onerror = () => {
      if (this.ws !== socket) return
      setStatus('error')
      socket.close()
    }
  }

  disconnect() {
    // Deliberate teardown: never reconnect, and detach handlers so this close
    // can't trigger the reconnect path.
    this.shouldReconnect = false
    this.stopHeartbeat()
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    const socket = this.ws
    this.ws = null
    if (socket) {
      socket.onopen = socket.onmessage = socket.onerror = socket.onclose = null
      socket.close()
    }
  }

  private startHeartbeat(socket: WebSocket) {
    this.stopHeartbeat()
    this.heartbeatTimer = setInterval(() => {
      if (this.ws !== socket) return
      this.send({ type: 'ping' })
      // Arm the watchdog: a pong must arrive before it fires, or we assume the
      // socket is half-open and close it to force a reconnect.
      if (this.pongTimer) clearTimeout(this.pongTimer)
      this.pongTimer = setTimeout(() => {
        this.pongTimer = null
        socket.close()
      }, PONG_TIMEOUT)
    }, HEARTBEAT_INTERVAL)
  }

  private stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
    if (this.pongTimer) {
      clearTimeout(this.pongTimer)
      this.pongTimer = null
    }
  }

  subscribe(channel: string) {
    useWebSocketStore.getState().subscribe(channel)
    this.send({ type: 'subscribe', channel })
  }

  unsubscribe(channel: string) {
    useWebSocketStore.getState().unsubscribe(channel)
    this.send({ type: 'unsubscribe', channel })
  }

  on(channel: string, handler: (data: unknown) => void): () => void {
    if (!this.handlers.has(channel)) this.handlers.set(channel, new Set())
    this.handlers.get(channel)!.add(handler)
    return () => this.handlers.get(channel)?.delete(handler)
  }

  private send(payload: unknown) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload))
    }
  }

  private dispatch(channel: string, data: unknown) {
    this.handlers.get(channel)?.forEach((h) => h(data))
  }

  private routeToStore(msg: WSMessage) {
    switch (msg.channel) {
      case 'portfolio.snapshot':
        usePortfolioStore.getState().setSnapshot(msg.data as import('@/types').PortfolioSnapshot)
        break
      case 'strategy.status':
        {
          const d = msg.data as import('@/types').StrategyStatusUpdate
          useStrategyStore.getState().updateStatus(d.id, d)
        }
        break
      case 'strategy.signal':
        useSignalsStore.getState().pushSignal(msg.data as SignalRecord)
        break
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) return // a reconnect is already pending
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, MAX_RECONNECT_DELAY)
      this.connect()
    }, this.reconnectDelay)
  }
}

export const tradingWS = new TradingWebSocket()
