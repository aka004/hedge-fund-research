import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import ScreenerPage from './components/ScreenerPage'
import StockDetailPage from './components/StockDetailPage'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/screener" replace />} />
        <Route path="/screener" element={<ScreenerPage />} />
        <Route path="/stock/:ticker" element={<StockDetailPage />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
