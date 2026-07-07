import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Toaster } from '@/components/ui/Toaster'
import { tradingWS } from '@/lib/websocket'

export function AppLayout() {
  useEffect(() => {
    tradingWS.connect()
    return () => tradingWS.disconnect()
  }, [])

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
      <Toaster />
    </div>
  )
}
