import { useEffect, useState } from 'react'
import { Spin, Switch, Tooltip, message } from 'antd'
import { PlusOutlined, QuestionCircleOutlined } from '@ant-design/icons'
import { agentConfigApi } from '@/api/agentConfig'
import { personaApi, type Persona } from '@/api/personas'
import PersonaCard from './agent/PersonaCard'
import PersonaEditModal from './agent/PersonaEditModal'

export default function AgentConfigPage() {
  const [personas, setPersonas] = useState<Persona[]>([])
  const [loading, setLoading] = useState(true)
  const [showAvatar, setShowAvatar] = useState(false)
  const [activeRecall, setActiveRecall] = useState(true)
  const [crossSession, setCrossSession] = useState(false)
  const [humanMode, setHumanMode] = useState(false)
  const [activatingId, setActivatingId] = useState<string | null>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState<Persona | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const [pResp, cResp] = await Promise.all([
        personaApi.list(),
        agentConfigApi.get(),
      ])
      setPersonas(pResp.data)
      setShowAvatar(cResp.data.show_avatar)
      setActiveRecall(cResp.data.enable_active_recall)
      setCrossSession(cResp.data.enable_cross_session)
      setHumanMode(cResp.data.human_mode)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const updateConfig = async (key: string, value: boolean, rollback: () => void) => {
    try {
      await agentConfigApi.update({ [key]: value })
    } catch (e) {
      rollback()
      message.error((e as Error).message)
    }
  }

  const onToggleAvatar = (value: boolean) => {
    setShowAvatar(value)
    void updateConfig('show_avatar', value, () => setShowAvatar(!value))
  }

  const onToggleActiveRecall = (value: boolean) => {
    setActiveRecall(value)
    void updateConfig('enable_active_recall', value, () => setActiveRecall(!value))
  }

  const onToggleCrossSession = (value: boolean) => {
    setCrossSession(value)
    void updateConfig('enable_cross_session', value, () => setCrossSession(!value))
  }

  const onToggleHumanMode = (value: boolean) => {
    setHumanMode(value)
    void updateConfig('human_mode', value, () => setHumanMode(!value))
  }

  const onActivate = async (persona: Persona) => {
    setActivatingId(persona.id)
    try {
      await personaApi.activate(persona.id)
      setPersonas((prev) => prev.map((item) => ({ ...item, is_active: item.id === persona.id })))
      message.success(`已切换到「${persona.name}」`)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setActivatingId(null)
    }
  }

  const onDelete = async (persona: Persona) => {
    try {
      await personaApi.remove(persona.id)
      message.success('已删除')
      await load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const personaTab = (
    <div className="persona-gallery">
      <button className="persona-ghost-card" onClick={() => { setEditing(null); setEditOpen(true) }}>
        <PlusOutlined className="persona-ghost-plus" />
        <span>新建角色</span>
      </button>
      {personas.map((persona, index) => (
        <PersonaCard
          key={persona.id}
          persona={persona}
          index={index}
          activating={activatingId === persona.id}
          onActivate={onActivate}
          onEdit={(item) => { setEditing(item); setEditOpen(true) }}
          onDelete={onDelete}
        />
      ))}
    </div>
  )

  return (
    <div className="fluid-page persona-page">
      <div className="persona-hero">
        <div className="persona-hero-bg" />
        <div className="persona-hero-content">
          <div>
            <div className="persona-hero-title">我的角色</div>
            <div className="persona-hero-sub">配置单聊中使用的角色人设与记忆行为</div>
          </div>
          <div className="persona-hero-switches">
            <div className="persona-hero-switch">
              <span>
                显示对话头像
                <Tooltip title="开启后，对话界面会显示当前角色头像与你的头像；关闭则两边都不显示">
                  <QuestionCircleOutlined style={{ marginLeft: 6, opacity: 0.7 }} />
                </Tooltip>
              </span>
              <Switch checked={showAvatar} onChange={onToggleAvatar} />
            </div>
            <div className="persona-hero-switch">
              <span>
                主动记忆
                <Tooltip title="开启后，每轮提问会自动检索与话题相关的记忆与「AI 眼中的你」，让回答更懂你；关闭则不注入">
                  <QuestionCircleOutlined style={{ marginLeft: 6, opacity: 0.7 }} />
                </Tooltip>
              </span>
              <Switch checked={activeRecall} onChange={onToggleActiveRecall} />
            </div>
            <div className="persona-hero-switch">
              <span>
                跨会话上下文
                <Tooltip title="开启后，提问时会参考你最近其他会话聊过的内容，跨会话也能接着聊；默认关闭，保持各会话独立">
                  <QuestionCircleOutlined style={{ marginLeft: 6, opacity: 0.7 }} />
                </Tooltip>
              </span>
              <Switch checked={crossSession} onChange={onToggleCrossSession} />
            </div>
            <div className="persona-hero-switch">
              <span>
                真人对话模式
                <Tooltip title="开启后对话更口语化、简短，并可能分多条气泡连发；关闭恢复助手风格">
                  <QuestionCircleOutlined style={{ marginLeft: 6, opacity: 0.7 }} />
                </Tooltip>
              </span>
              <Switch checked={humanMode} onChange={onToggleHumanMode} />
            </div>
          </div>
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 60 }}><Spin /></div>
      ) : (
        personaTab
      )}

      <PersonaEditModal
        open={editOpen}
        persona={editing}
        onClose={() => setEditOpen(false)}
        onSaved={load}
      />
    </div>
  )
}
