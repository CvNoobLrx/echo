import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Button,
  Card,
  Empty,
  Input,
  Popconfirm,
  Segmented,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import {
  CheckCircleOutlined,
  AuditOutlined,
  BulbOutlined,
  ClockCircleOutlined,
  DeleteOutlined,
  ExclamationCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import {
  memoryApi,
  type Insight,
  type MemoryHit,
  type MemoryItem,
  type MemoryProfile,
  type TimelineEvent,
} from '@/api/memories'
import ReviewPanel from '@/components/memory/ReviewPanel'

const { Text, Paragraph } = Typography

type TrustTone = 'high' | 'medium' | 'low'

function trustTone(confidence?: number | null): TrustTone {
  const value = typeof confidence === 'number' ? confidence : 0.8
  if (value >= 0.85) return 'high'
  if (value >= 0.75) return 'medium'
  return 'low'
}

function trustLabel(confidence?: number | null) {
  const tone = trustTone(confidence)
  if (tone === 'high') return '高置信'
  if (tone === 'medium') return '中置信'
  return '待确认'
}

function trustColor(confidence?: number | null) {
  const tone = trustTone(confidence)
  if (tone === 'high') return 'success'
  if (tone === 'medium') return 'processing'
  return 'warning'
}

function trustPercent(confidence?: number | null) {
  const value = typeof confidence === 'number' ? confidence : 0.8
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`
}

function TrustTag({ confidence }: { confidence?: number | null }) {
  const low = trustTone(confidence) === 'low'
  return (
    <Tooltip title={`置信度 ${trustPercent(confidence)}`}>
      <Tag
        color={trustColor(confidence)}
        icon={low ? <ExclamationCircleOutlined /> : <CheckCircleOutlined />}
        style={{ margin: 0 }}
      >
        {trustLabel(confidence)}
      </Tag>
    </Tooltip>
  )
}

export default function MemoryPage() {
  const [mode, setMode] = useState<'profile' | 'timeline' | 'search' | 'review'>(
    'profile',
  )

  // 手机端使用短标签，避免窄屏挤压。
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== 'undefined' && window.innerWidth <= 768,
  )
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)')
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  const tabOptions = [
    { label: isMobile ? '画像' : '我的画像', value: 'profile', icon: <BulbOutlined /> },
    { label: isMobile ? '时间' : '时间线', value: 'timeline', icon: <ClockCircleOutlined /> },
    { label: isMobile ? '检索' : '记忆检索', value: 'search', icon: <SearchOutlined /> },
    { label: isMobile ? '审查' : '审查纠错', value: 'review', icon: <AuditOutlined /> },
  ]

  return (
    <div className="fluid-page">
      <Card
        title="记忆"
        className="memory-card"
        extra={
          <Segmented
            className="memory-tabs"
            value={mode}
            onChange={(v) => setMode(v as 'profile' | 'timeline' | 'search' | 'review')}
            options={tabOptions}
          />
        }
      >
        {mode === 'profile' ? (
          <ProfilePanel />
        ) : mode === 'timeline' ? (
          <TimelinePanel />
        ) : mode === 'search' ? (
          <SearchPanel />
        ) : (
          <ReviewPanel />
        )}
      </Card>
    </div>
  )
}

// ── 我的画像：主动记住输入 + 实体按类型分组卡片 ──
function ProfilePanel() {
  const [profile, setProfile] = useState<MemoryProfile | null>(null)
  const [loading, setLoading] = useState(false)
  const [text, setText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [recentMemories, setRecentMemories] = useState<MemoryItem[]>([])
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const pollRef = useRef<number | null>(null)
  const pollCount = useRef(0)

  const load = async () => {
    setLoading(true)
    try {
      const [profileResult, memoryResult] = await Promise.all([
        memoryApi.profile(),
        memoryApi.list(1, 100),
      ])
      setProfile(profileResult.data)
      setRecentMemories(
        memoryResult.data.items.filter((item) => item.source === 'manual').slice(0, 5),
      )
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
  }, [])

  const startPolling = () => {
    pollCount.current = 0
    if (pollRef.current) window.clearInterval(pollRef.current)
    pollRef.current = window.setInterval(() => {
      pollCount.current += 1
      load()
      if (pollCount.current >= 6 && pollRef.current) {
        window.clearInterval(pollRef.current)
        pollRef.current = null
      }
    }, 4000)
  }

  const onRemember = async () => {
    const value = text.trim()
    if (!value) {
      message.warning('请输入要记住的内容')
      return
    }
    setSubmitting(true)
    try {
      await memoryApi.remember(value)
      message.success('已提交，正在萃取记忆，稍后自动刷新')
      setText('')
      startPolling()
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  const onRetry = async (id: string) => {
    try {
      await memoryApi.retry(id)
      message.success('已重新提交，正在萃取记忆')
      await load()
      startPolling()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const onDeleteEntity = async (id: string) => {
    try {
      await memoryApi.deleteEntity(id)
      message.success('已删除')
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const onDeleteMemory = async (id: string) => {
    setDeletingId(id)
    try {
      await memoryApi.remove(id)
      message.success('写入记录已删除')
      await load()
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      {/* AI 眼中的你（反思引擎归纳的高层理解） */}
      <InsightsBanner />

      {/* 主动记住 */}
      <Space.Compact style={{ width: '100%' }}>
        <Input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onPressEnter={onRemember}
          placeholder="告诉我一些值得长期记住的事，例如：我在腾讯做后端，养了只叫多多的小狗"
          size="large"
          allowClear
        />
        <Button
          type="primary"
          size="large"
          icon={<PlusOutlined />}
          loading={submitting}
          onClick={onRemember}
        >
          记住
        </Button>
      </Space.Compact>

      {recentMemories.length > 0 && (
        <div className="memory-write-status">
          <Text strong>最近写入</Text>
          {recentMemories.map((item) => {
            const status = {
              pending: { color: 'processing', label: '等待萃取' },
              extracting: { color: 'processing', label: '正在萃取' },
              done: { color: 'success', label: '已完成' },
              failed: { color: 'error', label: '萃取失败' },
            }[item.status]
            return (
              <div key={item.id} className="memory-write-status__item">
                <Popconfirm
                  title="删除这条写入记录？"
                  description="删除后无法恢复"
                  okText="删除"
                  cancelText="取消"
                  okButtonProps={{ danger: true }}
                  onConfirm={() => onDeleteMemory(item.id)}
                >
                  <Button
                    type="text"
                    danger
                    size="small"
                    className="memory-write-status__delete"
                    icon={<DeleteOutlined />}
                    loading={deletingId === item.id}
                    aria-label="删除写入记录"
                  />
                </Popconfirm>
                <div className="memory-write-status__content">
                  <Text ellipsis={{ tooltip: item.raw_text }}>{item.raw_text}</Text>
                  {item.status === 'failed' && item.error_msg && (
                    <Text type="danger" className="memory-write-status__error">
                      {item.error_msg}
                    </Text>
                  )}
                </div>
                <Space size={8} className="memory-write-status__actions">
                  <Tag color={status.color}>{status.label}</Tag>
                  {item.status === 'failed' && (
                    <Button
                      type="text"
                      size="small"
                      icon={<ReloadOutlined />}
                      onClick={() => onRetry(item.id)}
                    >
                      重试
                    </Button>
                  )}
                </Space>
              </div>
            )
          })}
        </div>
      )}

      {loading && !profile ? (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin />
        </div>
      ) : !profile || profile.total === 0 ? (
        <Empty description="还没有记忆。主动记住一些事，或在对话中聊聊你自己，我会自动记住" />
      ) : (
        <>
          <Text type="secondary">
            已记住 {profile.total} 个实体，覆盖 {profile.groups.length} 个类型
          </Text>
          {profile.groups.map((group) => (
            <div key={group.type}>
              <div style={{ marginBottom: 10 }}>
                <Tag color="blue" style={{ fontSize: 14, padding: '2px 10px' }}>
                  {group.type}
                </Tag>
                <Text type="secondary" style={{ fontSize: 13 }}>
                  {group.entities.length} 项
                </Text>
              </div>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(min(16rem, 100%), 1fr))',
                  gap: 12,
                  marginBottom: 8,
                }}
              >
                {group.entities.map((ent) => (
                  <Card
                    key={ent.id}
                    size="small"
                    className={trustTone(ent.confidence) === 'low' ? 'memory-entity-card memory-entity-card--weak' : 'memory-entity-card'}
                    styles={{ body: { padding: 14 } }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                      <Space size={4} wrap>
                        <Text strong style={{ fontSize: 15 }}>
                          {ent.name}
                        </Text>
                        <TrustTag confidence={ent.confidence} />
                        {ent.memory_layer === 'long_term' && (
                          <Tag color="gold" style={{ fontSize: 11, lineHeight: '16px', margin: 0 }}>
                            长期
                          </Tag>
                        )}
                      </Space>
                      <Space size={4}>
                        <Popconfirm title="删除该记忆实体？" onConfirm={() => onDeleteEntity(ent.id)}>
                          <DeleteOutlined style={{ color: '#C0C4CC' }} />
                        </Popconfirm>
                      </Space>
                    </div>
                    {ent.description && (
                      <Paragraph
                        type="secondary"
                        style={{ margin: '4px 0 0', fontSize: 13 }}
                        ellipsis={{ rows: 2, expandable: true, symbol: '展开' }}
                      >
                        {ent.description}
                      </Paragraph>
                    )}
                    {ent.aliases.length > 0 && (
                      <div style={{ marginTop: 6 }}>
                        {ent.aliases.map((a) => (
                          <Tag key={a} style={{ fontSize: 12 }}>
                            {a}
                          </Tag>
                        ))}
                      </div>
                    )}
                    {ent.relations.length > 0 && (
                      <div style={{ marginTop: 8, paddingLeft: 8, borderLeft: '2px solid #EEF4FF' }}>
                        {ent.relations.slice(0, 4).map((rel, i) => (
                          <div key={i} style={{ fontSize: 12.5, color: '#475467', lineHeight: 1.8 }}>
                            {trustTone(rel.confidence) === 'low' && (
                              <Tag color="warning" style={{ marginRight: 6, fontSize: 11, lineHeight: '16px' }}>
                                待确认
                              </Tag>
                            )}
                            <Text type="secondary">{rel.predicate}</Text> {rel.object_name}
                          </div>
                        ))}
                      </div>
                    )}
                  </Card>
                ))}
              </div>
            </div>
          ))}
        </>
      )}
    </Space>
  )
}

// ── AI 眼中的你：反思引擎归纳的高层理解 ──
function InsightsBanner() {
  const [insights, setInsights] = useState<Insight[]>([])
  const [loading, setLoading] = useState(true)
  const [reflecting, setReflecting] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const COLLAPSE_LIMIT = 6

  const load = async () => {
    try {
      const { data } = await memoryApi.insights()
      setInsights(data)
    } catch {
      // 洞察加载失败不影响画像
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const onReflect = async () => {
    setReflecting(true)
    try {
      const { data } = await memoryApi.reflect()
      if (data.insights > 0) {
        message.success(`已更新对你的理解，共 ${data.insights} 条`)
      } else {
        message.info('记忆还不够多，再多聊聊我就更懂你了')
      }
      load()
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setReflecting(false)
    }
  }

  const onDelete = async (id: string) => {
    try {
      await memoryApi.deleteInsight(id)
      setInsights((prev) => prev.filter((x) => x.id !== id))
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  // 加载中或空且未在反思：仍展示一个可触发反思的入口
  return (
    <div className="insight-banner">
      <div className="insight-banner-head">
        <Space size={8}>
          <BulbOutlined style={{ color: '#155EEF', fontSize: 18 }} />
          <span className="insight-banner-title">AI 眼中的你</span>
        </Space>
        <Button
          size="small"
          type="primary"
          ghost
          icon={<ThunderboltOutlined />}
          loading={reflecting}
          onClick={onReflect}
        >
          重新认识你
        </Button>
      </div>

      {loading ? (
        <div style={{ padding: 16, textAlign: 'center' }}>
          <Spin />
        </div>
      ) : insights.length === 0 ? (
        <div className="insight-banner-empty">
          还不太了解你。随着记忆积累，我会慢慢读懂你是个怎样的人（如「持续精进的技术人」），
          也可以点「重新认识你」马上生成。
        </div>
      ) : (
        <>
          <div className="insight-grid">
            {(expanded ? insights : insights.slice(0, COLLAPSE_LIMIT)).map((it) => (
              <div key={it.id} className="insight-item">
                <div className="insight-item-head">
                  <Tag color="geekblue" style={{ margin: 0 }}>
                    {it.theme}
                  </Tag>
                  <TrustTag confidence={it.confidence} />
                  <Popconfirm title="删除这条洞察？" onConfirm={() => onDelete(it.id)}>
                    <DeleteOutlined className="insight-del" />
                  </Popconfirm>
                </div>
                <div className="insight-content">{it.content}</div>
              </div>
            ))}
          </div>
          {insights.length > COLLAPSE_LIMIT && (
            <div style={{ textAlign: 'center', marginTop: 10 }}>
              <Button type="link" onClick={() => setExpanded((v) => !v)}>
                {expanded ? '收起' : `展开全部 ${insights.length} 条`}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ── 记忆检索 ──
function SearchPanel() {
  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [hits, setHits] = useState<MemoryHit[]>([])

  const onSearch = async () => {
    const q = query.trim()
    if (!q) {
      message.warning('请输入检索关键词')
      return
    }
    setSearching(true)
    try {
      const { data } = await memoryApi.search(q, 10)
      setHits(data)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setSearching(false)
    }
  }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Space.Compact style={{ width: '100%' }}>
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onPressEnter={onSearch}
          placeholder="按语义检索记忆，例如：我养的宠物、我的工作"
          size="large"
          allowClear
        />
        <Button type="primary" size="large" loading={searching} icon={<SearchOutlined />} onClick={onSearch}>
          检索
        </Button>
      </Space.Compact>

      {hits.length === 0 ? (
        <Empty description="输入关键词，从记忆图谱里召回相关实体与关系" />
      ) : (
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          {hits.map((h) => (
            <Card key={h.id} size="small" styles={{ body: { padding: 16 } }}>
              <Space size="small" style={{ marginBottom: 6 }}>
                <Text strong>{h.name}</Text>
                <Tag color="blue">{h.type}</Tag>
                <TrustTag confidence={h.confidence} />
                <Tooltip title="相关度">
                  <Tag>{h.score}</Tag>
                </Tooltip>
              </Space>
              {h.description && (
                <Paragraph type="secondary" style={{ margin: '4px 0' }}>
                  {h.description}
                </Paragraph>
              )}
              {h.aliases.length > 0 && (
                <div style={{ marginBottom: 6 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>别名：</Text>
                  {h.aliases.map((a) => (
                    <Tag key={a}>{a}</Tag>
                  ))}
                </div>
              )}
              {h.relations.length > 0 && (
                <div style={{ paddingLeft: 8, borderLeft: '2px solid #EEF4FF' }}>
                  {h.relations.map((rel, i) => (
                    <div key={i} style={{ fontSize: 13, color: '#475467' }}>
                      {trustTone(rel.confidence) === 'low' && (
                        <Tag color="warning" style={{ marginRight: 6, fontSize: 11, lineHeight: '16px' }}>
                          待确认
                        </Tag>
                      )}
                      {h.name} <Text type="secondary">{rel.predicate}</Text> {rel.object_name}
                    </div>
                  ))}
                </div>
              )}
            </Card>
          ))}
        </Space>
      )}
    </Space>
  )
}


// ── 时间线:按日期智能分桶(今天/昨天/近7天/本月/按月份),卡片化事件 ──
type TimeBucket = {
  key: string
  label: string
  hint?: string // 副标题,如 "6月21日 周六"
  order: number
  events: TimelineEvent[]
}

function bucketize(events: TimelineEvent[]): TimeBucket[] {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today.getTime() - 86_400_000)
  const week7Ago = new Date(today.getTime() - 6 * 86_400_000)
  const monthStart = new Date(now.getFullYear(), now.getMonth(), 1)
  const weekdays = ['日', '一', '二', '三', '四', '五', '六']

  const buckets: Record<string, TimeBucket> = {}
  const put = (
    key: string,
    label: string,
    order: number,
    ev: TimelineEvent,
    hint?: string,
  ) => {
    if (!buckets[key])
      buckets[key] = { key, label, hint, order, events: [] }
    buckets[key].events.push(ev)
  }

  for (const ev of events) {
    const raw = ev.event_time || ev.created_at
    if (!raw) {
      put('unknown', '时间未知', 99999, ev)
      continue
    }
    const d = new Date(raw)
    if (Number.isNaN(d.getTime())) {
      put('unknown', '时间未知', 99999, ev)
      continue
    }
    const day = new Date(d.getFullYear(), d.getMonth(), d.getDate())
    const hint = `${d.getMonth() + 1} 月 ${d.getDate()} 日 · 周${weekdays[d.getDay()]}`

    if (day.getTime() === today.getTime()) {
      put('today', '今天', 0, ev, hint)
    } else if (day.getTime() === yesterday.getTime()) {
      put('yesterday', '昨天', 1, ev, hint)
    } else if (day >= week7Ago && day < yesterday) {
      put('week', '近 7 天', 2, ev)
    } else if (day >= monthStart && day < week7Ago) {
      put('month', '本月更早', 3, ev)
    } else {
      const ym = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
      // 较新的月份排前面:用负时间戳缩放
      const order = 10 - d.getTime() / 1e13
      put(ym, `${d.getFullYear()} 年 ${d.getMonth() + 1} 月`, order, ev)
    }
  }

  return Object.values(buckets).sort((a, b) => a.order - b.order)
}

function TimelinePanel() {
  const [events, setEvents] = useState<TimelineEvent[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    memoryApi
      .timeline()
      .then(({ data }) => setEvents(data))
      .catch((e) => message.error((e as Error).message))
      .finally(() => setLoading(false))
  }, [])

  const buckets = useMemo(() => bucketize(events), [events])

  // 一天内只显示 HH:mm,跨天显示 M月D日
  const fmtEventTime = (ev: TimelineEvent, bucketKey: string) => {
    const raw = ev.event_time || ev.created_at
    if (!raw) return '时间未知'
    const d = new Date(raw)
    if (Number.isNaN(d.getTime())) return String(raw)
    if (bucketKey === 'today' || bucketKey === 'yesterday') {
      const hh = String(d.getHours()).padStart(2, '0')
      const mm = String(d.getMinutes()).padStart(2, '0')
      return `${hh}:${mm}`
    }
    return `${d.getMonth() + 1}月${d.getDate()}日`
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 40 }}>
        <Spin />
      </div>
    )
  }

  if (events.length === 0) {
    return (
      <Empty description="还没有事件。在对话或主动记住中提到带时间的经历,会自动记入时间线" />
    )
  }

  return (
    <div>
      {/* 顶部统计 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '10px 14px',
          background: '#f8fafc',
          border: '1px solid #e4e7ec',
          borderRadius: 8,
          marginBottom: 18,
        }}
      >
        <ClockCircleOutlined style={{ color: '#155EEF', fontSize: 16 }} />
        <Text strong style={{ fontSize: 14 }}>
          共 {events.length} 条带时间的事件
        </Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          · 按时间倒序展示,提到「日期」的对话会自动记入
        </Text>
      </div>

      {/* 分桶时间线 */}
      <Space direction="vertical" size={24} style={{ width: '100%' }}>
        {buckets.map((b) => (
          <div key={b.key}>
            {/* 桶头 */}
            <div
              style={{
                display: 'flex',
                alignItems: 'baseline',
                gap: 10,
                marginBottom: 12,
                paddingBottom: 6,
                borderBottom: '1px solid #f0f1f3',
              }}
            >
              <Text strong style={{ fontSize: 15, color: '#171719' }}>
                {b.label}
              </Text>
              {b.hint && (
                <Text type="secondary" style={{ fontSize: 12.5 }}>
                  {b.hint}
                </Text>
              )}
              <div style={{ flex: 1 }} />
              <span
                style={{
                  fontSize: 12,
                  color: '#667085',
                  background: '#f7f9fc',
                  padding: '1px 8px',
                  borderRadius: 999,
                }}
              >
                {b.events.length} 条
              </span>
            </div>

            {/* 事件列表 */}
            <div style={{ paddingLeft: 8 }}>
              {b.events.map((ev, idx) => (
                <div
                  key={ev.id}
                  style={{
                    position: 'relative',
                    paddingLeft: 28,
                    paddingBottom: idx === b.events.length - 1 ? 0 : 14,
                    borderLeft: idx === b.events.length - 1
                      ? 'none'
                      : '2px solid #EEF4FF',
                    marginLeft: 6,
                  }}
                >
                  {/* 节点圆点 */}
                  <span
                    style={{
                      position: 'absolute',
                      left: -7,
                      top: 8,
                      width: 12,
                      height: 12,
                      borderRadius: '50%',
                      background: '#155EEF',
                      border: '2px solid #ffffff',
                      boxShadow: '0 0 0 2px #EEF4FF',
                    }}
                  />
                  {/* 时间标签 */}
                  <Text
                    style={{
                      fontSize: 12,
                      color: '#155EEF',
                      fontWeight: 600,
                      letterSpacing: 0.3,
                    }}
                  >
                    {fmtEventTime(ev, b.key)}
                  </Text>
                  {/* 事件卡片 */}
                  <div
                    style={{
                      marginTop: 4,
                      background: '#ffffff',
                      border: '1px solid #eef0f4',
                      borderRadius: 10,
                      padding: '10px 14px',
                      transition:
                        'border-color 0.18s, box-shadow 0.18s, transform 0.18s',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = '#155EEF'
                      e.currentTarget.style.boxShadow =
                        '0 6px 14px -10px rgba(21, 94, 239, 0.3)'
                      e.currentTarget.style.transform = 'translateX(2px)'
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = '#eef0f4'
                      e.currentTarget.style.boxShadow = ''
                      e.currentTarget.style.transform = ''
                    }}
                  >
                    <Text
                      strong
                      style={{
                        fontSize: 14.5,
                        color: '#171719',
                        display: 'block',
                        marginBottom: ev.description || ev.participants.length ? 4 : 0,
                      }}
                    >
                      {ev.title}
                    </Text>
                    {ev.description && (
                      <Paragraph
                        type="secondary"
                        style={{
                          margin: 0,
                          fontSize: 13,
                          lineHeight: 1.6,
                          color: '#667085',
                        }}
                        ellipsis={{ rows: 2, tooltip: ev.description }}
                      >
                        {ev.description}
                      </Paragraph>
                    )}
                    {ev.participants.length > 0 && (
                      <Space size={4} wrap style={{ marginTop: 8 }}>
                        {ev.participants.map((p) => (
                          <Tag
                            key={p.id}
                            style={{
                              margin: 0,
                              fontSize: 11.5,
                              padding: '0 8px',
                              background: '#f0f7ff',
                              color: '#155EEF',
                              border: '1px solid #dbe6ff',
                              borderRadius: 999,
                            }}
                          >
                            {p.name}
                          </Tag>
                        ))}
                      </Space>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </Space>
    </div>
  )
}
