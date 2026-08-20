import { useCallback, useEffect, useRef, useState } from 'react'
import { App, Button, Form, Input, Select, Spin, Switch, Tag, Typography } from 'antd'
import { CheckCircleOutlined, ClockCircleOutlined, GlobalOutlined, MailOutlined, SendOutlined, SettingOutlined, WarningOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { newsApi, type NewsDelivery, type NewsSettings, type NewsSmtpInput } from '@/api/news'

const { Title, Text } = Typography
const STATUS_LABEL: Record<NewsDelivery['status'], string> = {
  queued: '等待处理', generating: '正在生成', sent: '已发送', failed: '发送失败',
}

function providerForEmail(email?: string | null): NewsSmtpInput['provider'] {
  const domain = email?.split('@')[1]?.toLowerCase()
  if (domain === '163.com') return '163'
  if (domain === 'gmail.com') return 'gmail'
  if (domain === 'outlook.com' || domain === 'hotmail.com') return 'outlook'
  return 'qq'
}

export default function NewsPushPage() {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [form] = Form.useForm<{ enabled: boolean; topics: string[] }>()
  const [smtpForm] = Form.useForm<NewsSmtpInput>()
  const [settings, setSettings] = useState<NewsSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [savingSmtp, setSavingSmtp] = useState(false)
  const [testing, setTesting] = useState(false)
  const [sending, setSending] = useState(false)
  const pollTimer = useRef<number | null>(null)

  const load = useCallback(async () => {
    try {
      const { data } = await newsApi.getSettings()
      setSettings(data)
      form.setFieldsValue({ enabled: data.enabled, topics: data.topics })
      smtpForm.setFieldsValue({
        provider: data.smtp.provider || providerForEmail(data.email),
        sender_email: data.smtp.sender_email || data.email || '',
        password: '',
        from_name: data.smtp.from_name || '回声 Echo',
      })
    } catch (error) {
      message.error((error as Error).message)
    } finally {
      setLoading(false)
    }
  }, [form, message, smtpForm])

  useEffect(() => {
    load()
    return () => { if (pollTimer.current) window.clearTimeout(pollTimer.current) }
  }, [load])

  const save = async (values: { enabled: boolean; topics: string[] }) => {
    setSaving(true)
    try {
      const { data } = await newsApi.updateSettings({ enabled: values.enabled, topics: values.topics || [] })
      setSettings(data)
      message.success('新闻推送设置已保存')
    } catch (error) {
      message.error((error as Error).message)
    } finally { setSaving(false) }
  }

  const testEmail = async () => {
    setTesting(true)
    try {
      await newsApi.testEmail()
      message.success('测试邮件已发送，请检查收件箱')
    } catch (error) {
      message.error((error as Error).message)
    } finally { setTesting(false) }
  }

  const saveSmtp = async (values: NewsSmtpInput) => {
    setSavingSmtp(true)
    try {
      const body = { ...values, password: values.password?.trim() || undefined }
      const { data } = await newsApi.updateSmtp(body)
      setSettings(data)
      smtpForm.setFieldValue('password', '')
      message.success('发件服务已保存')
    } catch (error) {
      const detail = (error as Error).message
      if (detail.includes('授权码') || detail.includes('应用密码')) {
        smtpForm.setFields([{ name: 'password', errors: [detail] }])
      } else {
        message.error(detail)
      }
    } finally { setSavingSmtp(false) }
  }

  const pollDelivery = async (id: string) => {
    try {
      const { data } = await newsApi.getDelivery(id)
      setSettings((current) => current ? { ...current, latest_delivery: data } : current)
      if (data.status === 'sent') { setSending(false); message.success('新闻晨报已发送'); return }
      if (data.status === 'failed') { setSending(false); message.error(data.error_message || '新闻晨报发送失败'); return }
      pollTimer.current = window.setTimeout(() => pollDelivery(id), 2500)
    } catch (error) {
      setSending(false)
      message.error((error as Error).message)
    }
  }

  const sendNow = async () => {
    setSending(true)
    try {
      const { data } = await newsApi.sendNow()
      message.info('正在检索并整理最近的新闻')
      await pollDelivery(data.delivery_id)
    } catch (error) {
      setSending(false)
      message.error((error as Error).message)
    }
  }

  if (loading) return <div className="dashboard-loading" role="status" aria-live="polite"><Spin size="large" /><Text type="secondary">正在加载新闻推送设置</Text></div>

  const ready = settings?.readiness
  const canSend = Boolean(settings?.email && ready?.smtp && ready.chat_model && ready.web_search)
  const latest = settings?.latest_delivery

  return (
    <div className="fluid-page news-settings-page">
      <header className="news-settings-heading">
        <div><Title level={1}>新闻推送</Title><Text type="secondary">每天早上整理最近 24 小时的重要新闻，并发送到账号邮箱。</Text></div>
        <div className="news-schedule"><ClockCircleOutlined /> {settings?.schedule}</div>
      </header>

      <section className="news-settings-section" aria-labelledby="news-recipient-title">
        <Title level={2} id="news-recipient-title">收件邮箱</Title>
        {settings?.email ? <div className="news-recipient"><MailOutlined /><strong>{settings.email}</strong></div> : (
          <div className="news-warning" role="status"><WarningOutlined /><span>账号尚未设置邮箱。设置邮箱后才能启用或发送新闻晨报。</span><Button type="link" onClick={() => navigate('/profile')}>前往个人资料</Button></div>
        )}
      </section>

      <section className="news-settings-section" aria-labelledby="news-preferences-title">
        <Title level={2} id="news-preferences-title">晨报偏好</Title>
        <Form form={form} layout="vertical" onFinish={save} requiredMark={false}>
          <Form.Item name="enabled" label="每天发送新闻晨报" valuePropName="checked" tooltip="每天 08:00 开始检索和整理，邮件会在生成完成后送达。"><Switch disabled={!settings?.email} /></Form.Item>
          <Form.Item name="topics" label="兴趣主题" extra="最多 6 个，每个不超过 30 个字符。留空时只发送综合要闻。" rules={[{ validator: (_, value: string[] = []) => value.length > 6 ? Promise.reject(new Error('最多设置 6 个兴趣主题')) : value.some((topic) => topic.trim().length > 30) ? Promise.reject(new Error('每个兴趣主题不能超过 30 个字符')) : Promise.resolve() }]}>
            <Select mode="tags" maxCount={6} tokenSeparators={[',', '，']} placeholder="例如：人工智能、宏观经济" aria-label="兴趣主题" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={saving}>保存设置</Button>
        </Form>
      </section>

      <section className="news-settings-section" aria-labelledby="news-readiness-title">
        <Title level={2} id="news-readiness-title">发送准备</Title>
        <div className="news-readiness-list">
          {([['SMTP 发件服务', ready?.smtp], ['默认对话模型', ready?.chat_model], ['联网搜索模型', ready?.web_search]] as const).map(([label, ok]) => (
            <div key={label}><span>{label}</span><Tag icon={ok ? <CheckCircleOutlined /> : <WarningOutlined />} color={ok ? 'success' : 'warning'}>{ok ? '已就绪' : '未配置'}</Tag></div>
          ))}
        </div>
        <div className="news-actions">
          <Button icon={<MailOutlined />} onClick={testEmail} loading={testing} disabled={!settings?.email || !ready?.smtp}>发送测试邮件</Button>
          <Button type="primary" icon={<SendOutlined />} onClick={sendNow} loading={sending} disabled={!canSend}>立即发送晨报</Button>
        </div>
      </section>

      <section className="news-settings-section" aria-labelledby="news-smtp-title">
        <Title level={2} id="news-smtp-title">配置 SMTP 发件服务</Title>
        <Text type="secondary">使用你的邮箱发送晨报。授权码会加密保存，页面不会读取或显示原文。</Text>
        <Form form={smtpForm} layout="vertical" onFinish={saveSmtp} requiredMark={false} className="news-smtp-form">
          <Form.Item name="provider" label="邮箱服务商" rules={[{ required: true, message: '请选择邮箱服务商' }]}>
            <Select options={[
              { value: 'qq', label: 'QQ 邮箱' },
              { value: '163', label: '网易 163 邮箱' },
              { value: 'gmail', label: 'Gmail' },
              { value: 'outlook', label: 'Outlook / Hotmail' },
            ]} />
          </Form.Item>
          <Form.Item name="sender_email" label="发件邮箱" rules={[
            { required: true, message: '请输入发件邮箱' },
            { type: 'email', message: '请输入有效的邮箱地址' },
          ]}>
            <Input type="email" autoComplete="email" placeholder="name@example.com" />
          </Form.Item>
          <Form.Item name="password" label={settings?.smtp.configured ? '授权码或应用密码（已保存，留空不修改）' : '授权码或应用密码'} rules={settings?.smtp.configured ? [] : [{ required: true, message: '请输入邮箱授权码或应用密码' }]} extra="请使用邮箱服务商生成的授权码或应用密码，不要填写邮箱登录密码。">
            <Input.Password autoComplete="new-password" placeholder={settings?.smtp.configured ? '留空则继续使用已保存的授权码' : '输入授权码或应用密码'} />
          </Form.Item>
          <Form.Item name="from_name" label="发件人名称" rules={[{ required: true, message: '请输入发件人名称' }]}>
            <Input maxLength={128} autoComplete="organization" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={savingSmtp}>保存发件服务</Button>
        </Form>
        <Text type="secondary" className="news-smtp-help">QQ 邮箱需先在邮箱网页版开启 SMTP 服务并生成授权码；Gmail 和 Outlook 请使用应用密码。</Text>
      </section>

      <section className="news-settings-section" aria-labelledby="news-source-title">
        <Title level={2} id="news-source-title">新闻来源</Title>
        <div className="news-source-intro"><GlobalOutlined /><Text>系统不使用固定媒体名单，而是通过你配置的联网搜索服务检索最近 24 小时的新闻，并在邮件中保留每条原文链接。</Text></div>
        <div className="news-source-options">
          <div><strong>百度千帆</strong><Text type="secondary">中文新闻覆盖更友好，根据“最近 24 小时”查询词检索网页。</Text></div>
          <div><strong>Tavily</strong><Text type="secondary">兼顾国际来源，并向搜索接口明确传入新闻类型和最近 1 天范围。</Text></div>
        </div>
        <Text type="secondary">搜索结果会按链接去重，再由默认对话模型仅根据这些来源生成摘要。来源不足时会减少条数，不会编造内容补足数量。</Text>
        <div className="news-source-action"><Button icon={<SettingOutlined />} onClick={() => navigate('/settings/models')}>配置联网搜索模型</Button></div>
      </section>

      {latest && <section className="news-settings-section" aria-labelledby="news-latest-title">
        <Title level={2} id="news-latest-title">最近一次发送</Title>
        <div className="news-latest-status" role="status" aria-live="polite"><Tag color={latest.status === 'sent' ? 'success' : latest.status === 'failed' ? 'error' : 'processing'}>{STATUS_LABEL[latest.status]}</Tag><span>{latest.recipient_email}</span><span>{latest.created_at ? new Date(latest.created_at).toLocaleString() : ''}</span></div>
        {latest.error_message && <Text type="danger">{latest.error_message}</Text>}
      </section>}
    </div>
  )
}
