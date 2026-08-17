import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import MainLayout from './layouts/MainLayout'
import DashboardPage from './pages/DashboardPage'
import LoginPage from './pages/LoginPage'
import ModelConfigPage from './pages/ModelConfigPage'
import KnowledgeBasePage from './pages/KnowledgeBasePage'
import KnowledgeDetailPage from './pages/KnowledgeDetailPage'
import ImagePage from './pages/ImagePage'
import MemoryPage from './pages/MemoryPage'
import GraphPage from './pages/GraphPage'
import ChatPage from './pages/ChatPage'
import ResearchPage from './pages/ResearchPage'
import FavoritesPage from './pages/FavoritesPage'
import NotifyChannelPage from './pages/NotifyChannelPage'
import SkillPage from './pages/SkillPage'
import TracesPage from './pages/TracesPage'
import AgentConfigPage from './pages/AgentConfigPage'
import ToolConfigPage from './pages/ToolConfigPage'
import ProfilePage from './pages/ProfilePage'
import RequireAuth from './components/RequireAuth'
import ErrorBoundary from './components/ErrorBoundary'

// 阶段1：登录页 + 路由守卫；主布局需登录后访问
export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/"
            element={
              <RequireAuth>
                <MainLayout />
              </RequireAuth>
            }
          >
            <Route index element={<DashboardPage />} />
            <Route path="chat" element={<ChatPage />} />
            <Route path="research" element={<ResearchPage />} />
            <Route path="knowledge" element={<KnowledgeBasePage />} />
            <Route path="knowledge-bases/:kbId" element={<KnowledgeDetailPage />} />
            <Route path="images" element={<ImagePage />} />
            <Route path="memory" element={<MemoryPage />} />
            <Route path="graph" element={<GraphPage />} />
            <Route path="favorites" element={<FavoritesPage />} />
            <Route path="traces" element={<TracesPage />} />
            <Route path="profile" element={<ProfilePage />} />
            <Route path="settings/models" element={<ModelConfigPage />} />
            <Route path="settings/agent" element={<AgentConfigPage />} />
            <Route path="settings/skills" element={<SkillPage />} />
            <Route path="settings/tools" element={<ToolConfigPage />} />
            <Route path="settings/notify" element={<NotifyChannelPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  )
}
