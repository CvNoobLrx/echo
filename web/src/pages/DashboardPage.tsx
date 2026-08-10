import { useEffect, useState } from 'react'
import { App, Button, Card, Col, Empty, List, Row, Spin, Statistic, Tag, Typography } from 'antd'
import {
  BookOutlined,
  CommentOutlined,
  DeploymentUnitOutlined,
  FileSearchOutlined,
  PictureOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import {
  dashboardApi,
  type AgentBriefItem,
  type LoopHealthData,
  type OverviewData,
  type DailyReviewData,
} from '@/api/dashboard'
import { useAuthStore } from '@/stores/authStore'

const { Title, Text } = Typography

export default function DashboardPage() {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(true)
  const [overview, setOverview] = useState<OverviewData | null>(null)
  const [briefing, setBriefing] = useState<AgentBriefItem[]>([])
  const [loop, setLoop] = useState<LoopHealthData | null>(null)
  const [review, setReview] = useState<DailyReviewData | null>(null)
  const [reviewLoading, setReviewLoading] = useState(false)
  const user = useAuthStore((state) => state.user)

  useEffect(() => {
    Promise.all([
      dashboardApi.overview(),
      dashboardApi.agentBriefing(),
      dashboardApi.loopHealth(),
      dashboardApi.dailyReview(),
    ])
      .then(([overviewRes, briefingRes, loopRes, reviewRes]) => {
        setOverview(overviewRes.data)
        setBriefing(briefingRes.data)
        setLoop(loopRes.data)
        setReview(reviewRes.data)
      })
      .catch((error: Error) => message.error(error.message))
      .finally(() => setLoading(false))
  }, [message])

  useEffect(() => {
    if (review?.status !== 'generating') return
    const timer = window.setInterval(() => {
      dashboardApi.dailyReview().then(({ data }) => setReview(data)).catch(() => {})
    }, 3000)
    return () => window.clearInterval(timer)
  }, [review?.status])

  if (loading) {
    return <Spin fullscreen tip="正在加载仪表盘" />
  }

  const counts = overview?.counts
  const displayName = user?.nickname || user?.username || '朋友'
  const hour = new Date().getHours()
  const greeting = hour < 6 ? '夜深了' : hour < 12 ? '早上好' : hour < 18 ? '下午好' : '晚上好'
  const stats = [
    { title: '文档', value: counts?.documents ?? 0, icon: <BookOutlined /> },
    { title: '图片', value: counts?.images ?? 0, icon: <PictureOutlined /> },
    { title: '对话', value: counts?.conversations ?? 0, icon: <CommentOutlined /> },
    { title: '图谱实体', value: counts?.entities ?? 0, icon: <DeploymentUnitOutlined /> },
  ]

  return (
    <div className="fluid-page">
      <Title level={2} style={{ marginTop: 0 }}>{greeting}，{displayName}</Title>
      <Text type="secondary">知识、记忆和 Agent 执行情况概览</Text>

      <Card
        title={`今日回顾 · ${displayName}`}
        extra={<Button type="text" icon={<ReloadOutlined />} loading={reviewLoading || review?.status === 'generating'} disabled={review?.status === 'generating'} title="重新生成" onClick={async () => { setReviewLoading(true); try { setReview((await dashboardApi.regenerateDailyReview()).data) } finally { setReviewLoading(false) } }} />}
        style={{ marginTop: 20 }}
      >
        {review ? (
          <>
            <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 12 }}>{review.content}</Typography.Paragraph>
            {review.status === 'generating' && <Text type="secondary">正在用默认对话模型完善总结…</Text>}
            {review.care && <Button type="link" icon={<CommentOutlined />} onClick={() => { window.location.href = `/chat?greeting=${encodeURIComponent(review.care)}` }}>聊聊</Button>}
            <div style={{ display: 'flex', gap: 16, color: '#667085', fontSize: 13 }}>
              <span>提问 {review.stats.messages}</span><span>记忆 {review.stats.memories}</span><span>文档 {review.stats.documents}</span>
            </div>
          </>
        ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="今天还没有总结" />}
      </Card>

      <Row gutter={[16, 16]} style={{ marginTop: 20 }}>
        {stats.map((item) => (
          <Col xs={12} lg={6} key={item.title}>
            <Card size="small">
              <Statistic title={item.title} value={item.value} prefix={item.icon} />
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Card title="最近活动">
            {overview?.recent.length ? (
              <List
                dataSource={overview.recent}
                renderItem={(item) => (
                  <List.Item>
                    <List.Item.Meta title={item.title} description={item.time || '时间未知'} />
                    <Tag>{item.type === 'document' ? '文档' : item.type}</Tag>
                  </List.Item>
                )}
              />
            ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无活动" />}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="最近研究" extra={<FileSearchOutlined />}>
            {briefing.length ? (
              <List
                dataSource={briefing}
                renderItem={(item) => (
                  <List.Item>
                    <List.Item.Meta title={item.title} description={item.created_at || '时间未知'} />
                  </List.Item>
                )}
              />
            ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无研究报告" />}
          </Card>
        </Col>
      </Row>

      <Card title="Verifier Loop 健康度" style={{ marginTop: 16 }}>
        <Row gutter={[16, 16]}>
          <Col xs={12} md={6}><Statistic title="执行次数" value={loop?.total ?? 0} /></Col>
          <Col xs={12} md={6}><Statistic title="通过" value={loop?.passed ?? 0} /></Col>
          <Col xs={12} md={6}><Statistic title="一次通过率" value={(loop?.one_shot_pass_rate ?? 0) * 100} suffix="%" precision={1} /></Col>
          <Col xs={12} md={6}><Statistic title="平均迭代" value={loop?.avg_iterations ?? 0} precision={1} /></Col>
        </Row>
      </Card>
    </div>
  )
}
