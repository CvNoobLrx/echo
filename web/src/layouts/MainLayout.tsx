import { Avatar, Button, Drawer, Dropdown, Layout, Menu, Space } from 'antd'
import {
  AppstoreOutlined,
  BellOutlined,
  BookOutlined,
  CommentOutlined,
  DeploymentUnitOutlined,
  FileSearchOutlined,
  HddOutlined,
  HistoryOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PictureOutlined,
  PlusOutlined,
  RobotOutlined,
  SettingOutlined,
  StarOutlined,
  ThunderboltOutlined,
  ToolOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { useEffect, useState } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { AuthenticatedImage } from '@/components/AuthenticatedImage'
import { useAuthStore } from '@/stores/authStore'
import { useChatHeaderStore } from '@/stores/chatHeaderStore'
import logo from '@/images/logo.svg'

const { Sider, Content, Header } = Layout

const menuItems = [
  {
    type: 'group' as const,
    label: '工作台',
    children: [
      { key: '/', icon: <AppstoreOutlined />, label: '仪表盘' },
      { key: '/chat', icon: <CommentOutlined />, label: '对话' },
      { key: '/research', icon: <FileSearchOutlined />, label: '深度研究' },
      { key: '/traces', icon: <HistoryOutlined />, label: '执行轨迹' },
    ],
  },
  {
    type: 'group' as const,
    label: '收藏',
    children: [{ key: '/favorites', icon: <StarOutlined />, label: '收藏夹' }],
  },
  {
    type: 'group' as const,
    label: '知识与记忆',
    children: [
      { key: '/knowledge', icon: <BookOutlined />, label: '知识库' },
      { key: '/images', icon: <PictureOutlined />, label: '图片库' },
      { key: '/memory', icon: <HddOutlined />, label: '记忆' },
      { key: '/graph', icon: <DeploymentUnitOutlined />, label: '知识图谱' },
    ],
  },
  {
    type: 'group' as const,
    label: '设置',
    children: [
      { key: '/settings/models', icon: <SettingOutlined />, label: '模型配置' },
      { key: '/settings/agent', icon: <RobotOutlined />, label: '角色配置' },
      { key: '/settings/skills', icon: <ThunderboltOutlined />, label: '技能' },
      { key: '/settings/tools', icon: <ToolOutlined />, label: '工具配置' },
      { key: '/settings/notify', icon: <BellOutlined />, label: '消息推送' },
    ],
  },
]

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== 'undefined' && window.innerWidth <= 768,
  )

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)')
    const handler = (event: MediaQueryListEvent) => setIsMobile(event.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  return isMobile
}

export default function MainLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)
  const isMobile = useIsMobile()
  const [collapsed, setCollapsed] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)

  const chatHeaderActive = useChatHeaderStore((state) => state.active)
  const chatOpenHistory = useChatHeaderStore((state) => state.openHistory)
  const chatNewChat = useChatHeaderStore((state) => state.newChat)
  const showChatHeader = isMobile && chatHeaderActive && location.pathname === '/chat'

  useEffect(() => setDrawerOpen(false), [location.pathname])

  const selectedKey =
    menuItems
      .flatMap((group) => group.children)
      .find((item) => location.pathname === item.key || location.pathname.startsWith(`${item.key}/`))
      ?.key ?? '/chat'
  const currentPage = menuItems
    .flatMap((group) => group.children)
    .find((item) => item.key === selectedKey)

  const profileMenu = {
    items: [
      { key: 'profile', icon: <UserOutlined />, label: '个人资料' },
      { type: 'divider' as const },
      { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', danger: true },
    ],
    onClick: ({ key }: { key: string }) => {
      if (key === 'profile') navigate('/profile')
      if (key === 'logout') {
        logout()
        navigate('/login')
      }
    },
  }

  const navigation = (
    <>
      <Link to="/" className="app-brand" aria-label="返回仪表盘">
        <img src={logo} alt="" className="app-brand-logo" />
        <span className="app-brand-wordmark" aria-hidden={collapsed}>
          <strong>回声</strong>
          <small>Echo</small>
        </span>
      </Link>
      <Menu
        mode="inline"
        items={menuItems}
        selectedKeys={[selectedKey]}
        onClick={({ key }) => navigate(key)}
        className="app-menu"
      />
    </>
  )

  return (
    <Layout className="app-shell">
      <a href="#main-content" className="app-skip-link">跳到主要内容</a>
      {!isMobile && (
        <Sider collapsible collapsed={collapsed} trigger={null} width={224} className="app-sider">
          {navigation}
        </Sider>
      )}
      <Drawer
        placement="left"
        width={240}
        open={isMobile && drawerOpen}
        onClose={() => setDrawerOpen(false)}
        styles={{ body: { padding: 0 } }}
      >
        {navigation}
      </Drawer>

      <Layout>
        <Header className="app-header">
          <Button
            type="text"
            className="app-nav-toggle"
            icon={isMobile || collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => (isMobile ? setDrawerOpen(true) : setCollapsed((value) => !value))}
            aria-label="切换导航"
          />

          {!showChatHeader && (
            <div className="app-page-context">
              <span className="app-page-title">{currentPage?.label || '工作台'}</span>
            </div>
          )}

          {showChatHeader ? (
            <Space>
              <Button type="text" icon={<HistoryOutlined />} onClick={chatOpenHistory} aria-label="打开历史对话" />
              <Button type="text" icon={<PlusOutlined />} onClick={chatNewChat} aria-label="新建对话" />
            </Space>
          ) : null}

          <Dropdown menu={profileMenu} placement="bottomRight">
            <Button type="text" className="app-user-button" aria-label="打开账号菜单">
              <Space>
                {user?.avatar ? (
                  <AuthenticatedImage src={user.avatar} alt="头像" className="app-user-avatar" />
                ) : (
                  <Avatar size={28} icon={<UserOutlined />} />
                )}
                {!isMobile && <span>{user?.nickname || user?.username}</span>}
              </Space>
            </Button>
          </Dropdown>
        </Header>
        <Content id="main-content" tabIndex={-1} className="app-content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
