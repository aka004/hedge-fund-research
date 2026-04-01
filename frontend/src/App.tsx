import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import ScreenerPage from './components/ScreenerPage'
import StockDetailPage from './components/StockDetailPage'
import DashboardPage from './components/dashboard/DashboardPage'
import { MacroPage } from './pages/MacroPage'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/screener" replace />} />
        <Route path="/screener" element={<ScreenerPage />} />
        <Route path="/stock/:ticker" element={<StockDetailPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/macro" element={<MacroPage />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
