import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import ScreenerPage from './components/ScreenerPage'
import StockDetailPage from './components/StockDetailPage'
import DashboardPage from './components/dashboard/DashboardPage'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/screener" replace />} />
        <Route path="/screener" element={<ScreenerPage />} />
        <Route path="/stock/:ticker" element={<StockDetailPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
