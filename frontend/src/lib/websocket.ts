import { useWebSocketStore } from '@/stores/websocket'
import { usePortfolioStore } from '@/stores/portfolio'
import { useStrategyStore } from '@/stores/strategy'
import { useSignalsStore } from '@/stores/signals'
import type { WSMessage, SignalRecord } from '@/types'

const MAX_RECONNECT_DELAY = 30_000

class TradingWebSocket {
  private ws: WebSocket | null = null
  private reconnectDelay = 1_000
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private handlers = new Map<string, Set<(data: unknown) => void>>()

  connect() {
    const { setStatus } = useWebSocketStore.getState()
    setStatus('connecting')

    this.ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`)

    this.ws.onopen = () => {
      setStatus('connected')
      this.reconnectDelay = 1_000
      const { subscribedSymbols } = useWebSocketStore.getState()
      subscribedSymbols.forEach((s) => this.subscribe(s))
    }

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const msg = JSON.parse(event.data as string) as WSMessage
        this.dispatch(msg.channel, msg.data)
        this.routeToStore(msg)
      } catch {
        // malformed frame — ignore
      }
    }

    this.ws.onclose = () => {
      setStatus('disconnected')
      this.scheduleReconnect()
    }

    this.ws.onerror = () => {
      setStatus('error')
      this.ws?.close()
    }
  }

  disconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.ws?.close()
    this.ws = null
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
    this.reconnectTimer = setTimeout(() => {
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, MAX_RECONNECT_DELAY)
      this.connect()
    }, this.reconnectDelay)
  }
}

export const tradingWS = new TradingWebSocket()
