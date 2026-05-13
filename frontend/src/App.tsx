import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AppLayout } from '@/components/layout/AppLayout'
import { Landing } from '@/pages/Landing/Landing'
import { Dashboard } from '@/pages/Dashboard/Dashboard'
import { Portfolio } from '@/pages/Portafolio/Portfolio'
import { Backtests } from '@/pages/Backtests/Backtests'
import { Strategies } from '@/pages/Strategies/Strategies'
import { Builder } from '@/pages/Builder/Builder'
import { Settings } from '@/pages/Settings/Settings'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route element={<AppLayout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/portfolio" element={<Portfolio />} />
          <Route path="/backtests" element={<Backtests />} />
          <Route path="/strategies" element={<Strategies />} />
          <Route path="/builder" element={<Builder />} />
          <Route path="/settings" element={<Settings />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
