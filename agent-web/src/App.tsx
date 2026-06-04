import { BrowserRouter, Route, Routes } from 'react-router-dom'

import { AdminPage } from './pages/AdminPage'
import { ChatPage } from './pages/ChatPage'

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-full p-4 md:p-8">
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/admin" element={<AdminPage />} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}

export default App
