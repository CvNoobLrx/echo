import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Button, Checkbox, Form, Input, Tabs, message } from 'antd'
import { LockOutlined, MailOutlined } from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import logo from '@/images/logo.svg'

interface FormValues {
  email: string
  password: string
}

const LS_REMEMBER = 'echo_remember'

function AnimatedEchoLogo({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 64 64" aria-hidden="true">
      <rect width="64" height="64" rx="12" fill="#101828" />
      <g className="applogin-signal-arcs">
        <path d="M17 32c0-8.3 6.7-15 15-15" fill="none" stroke="#62D3C5" strokeWidth="5" strokeLinecap="round" />
        <path d="M24 32a8 8 0 0 1 8-8" fill="none" stroke="#F9FAFB" strokeWidth="5" strokeLinecap="round" />
        <path d="M32 47c8.3 0 15-6.7 15-15" fill="none" stroke="#62D3C5" strokeWidth="5" strokeLinecap="round" />
        <path d="M32 40a8 8 0 0 0 8-8" fill="none" stroke="#F9FAFB" strokeWidth="5" strokeLinecap="round" />
      </g>
      <circle cx="32" cy="32" r="4" fill="#FFB84D" />
    </svg>
  )
}

export default function LoginPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const login = useAuthStore((s) => s.login)
  const register = useAuthStore((s) => s.register)
  const [tab, setTab] = useState('login')
  const [loading, setLoading] = useState(false)
  const [loginForm] = Form.useForm()
  const [rememberAccount, setRememberAccount] = useState(true)
  const [rememberPassword, setRememberPassword] = useState(false)
  const [introDone, setIntroDone] = useState(false)
  const logoTargetRef = useRef<HTMLImageElement>(null)
  const introLogoRef = useRef<HTMLDivElement>(null)

  useLayoutEffect(() => {
    const target = logoTargetRef.current
    const intro = introLogoRef.current
    if (!target || !intro) return

    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setIntroDone(true)
      return
    }

    let cancelled = false
    let landingAnimation: Animation | undefined
    let targetRevealAnimation: Animation | undefined
    const nextFrame = () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))

    const startIntro = async () => {
      await document.fonts?.ready
      await nextFrame()
      await nextFrame()
      if (cancelled) return

      const targetRect = target.getBoundingClientRect()
      const x = targetRect.left + targetRect.width / 2 - window.innerWidth / 2
      const y = targetRect.top + targetRect.height / 2 - window.innerHeight / 2
      const scale = targetRect.width / intro.getBoundingClientRect().width
      const landedTransform = `translate(calc(-50% + ${x}px), calc(-50% + ${y}px)) scale(${scale})`

      landingAnimation = intro.animate(
        [
          { opacity: 1, transform: 'translate(-50%, -50%) scale(1)', offset: 0 },
          {
            transform: 'translate(-50%, -50%) scale(1)',
            offset: 0.56,
            easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
          },
          {
            transform: landedTransform,
            opacity: 1,
            offset: 0.94,
            easing: 'cubic-bezier(0.2, 0, 0, 1)',
          },
          { transform: landedTransform, opacity: 0, offset: 1 },
        ],
        { duration: 2400, fill: 'forwards', easing: 'linear' },
      )
      targetRevealAnimation = target.animate(
        [{ opacity: 0 }, { opacity: 1 }],
        { duration: 220, delay: 2180, fill: 'forwards', easing: 'cubic-bezier(0.2, 0, 0, 1)' },
      )
      landingAnimation.onfinish = () => {
        if (!cancelled) setIntroDone(true)
      }
    }

    void startIntro()
    return () => {
      cancelled = true
      landingAnimation?.cancel()
      targetRevealAnimation?.cancel()
    }
  }, [])

  useEffect(() => {
    try {
      const raw = localStorage.getItem(LS_REMEMBER)
      if (!raw) return
      const saved = JSON.parse(raw) as { email?: string; password?: string }
      if (saved.email) {
        loginForm.setFieldsValue({ email: saved.email, password: saved.password ?? '' })
        setRememberAccount(true)
        setRememberPassword(!!saved.password)
      }
    } catch {
      // 回填失败忽略
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const onLogin = async (v: FormValues) => {
    setLoading(true)
    try {
      await login(v.email.trim(), v.password)
      if (rememberAccount) {
        localStorage.setItem(
          LS_REMEMBER,
          JSON.stringify({
            email: v.email.trim(),
            password: rememberPassword ? v.password : undefined,
          }),
        )
      } else {
        localStorage.removeItem(LS_REMEMBER)
      }
      message.success('登录成功')
      const redirect = searchParams.get('redirect')
      navigate(redirect || '/', { replace: true })
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const onRegister = async (v: FormValues) => {
    setLoading(true)
    try {
      await register(v.email.trim(), v.password)
      message.success('注册成功，请登录')
      setTab('login')
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const renderForm = (
    onFinish: (v: FormValues) => void,
    submitText: string,
    isLogin: boolean,
  ) => (
    <Form
      form={isLogin ? loginForm : undefined}
      layout="vertical"
      onFinish={onFinish}
      disabled={loading}
      requiredMark={false}
      size="large"
    >
      <Form.Item
        label="邮箱"
        name="email"
        validateTrigger="onBlur"
        rules={[
          { required: true, message: '请输入邮箱' },
          { type: 'email', message: '邮箱格式不正确' },
        ]}
      >
        <Input
          prefix={<MailOutlined />}
          type="email"
          name="email"
          inputMode="email"
          placeholder="name@example.com"
          autoComplete="email"
          allowClear
        />
      </Form.Item>
      <Form.Item
        label="密码"
        name="password"
        rules={[
          { required: true, message: '请输入密码' },
          { min: 6, message: '密码不能少于 6 位' },
        ]}
      >
        <Input.Password
          prefix={<LockOutlined />}
          name="password"
          placeholder="至少 6 位"
          autoComplete={isLogin ? 'current-password' : 'new-password'}
        />
      </Form.Item>
      {!isLogin && (
        <Form.Item
          label="确认密码"
          name="confirm"
          dependencies={['password']}
          rules={[
            { required: true, message: '请再次输入密码' },
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (!value || getFieldValue('password') === value) {
                  return Promise.resolve()
                }
                return Promise.reject(new Error('两次输入的密码不一致'))
              },
            }),
          ]}
        >
          <Input.Password
            prefix={<LockOutlined />}
            name="confirmPassword"
            placeholder="再次输入密码"
            autoComplete="new-password"
          />
        </Form.Item>
      )}
      {isLogin && (
        <div className="login2-remember">
          <Checkbox
            checked={rememberAccount}
            onChange={(e) => {
              setRememberAccount(e.target.checked)
              if (!e.target.checked) setRememberPassword(false)
            }}
          >
            记住账号
          </Checkbox>
          <Checkbox
            checked={rememberPassword}
            disabled={!rememberAccount}
            onChange={(e) => setRememberPassword(e.target.checked)}
          >
            记住密码
          </Checkbox>
        </div>
      )}
      <Form.Item style={{ marginBottom: 0, marginTop: 4 }}>
        <Button
          type="primary"
          htmlType="submit"
          block
          size="large"
          loading={loading}
          style={{ height: 46, fontSize: 16, fontWeight: 600 }}
        >
          {submitText}
        </Button>
      </Form.Item>
    </Form>
  )

  return (
    <div className={`applogin ${introDone ? 'applogin--ready' : 'applogin--intro'}`}>
      <div className="applogin-bg" />
      {!introDone && (
        <div
          ref={introLogoRef}
          className="applogin-logo-intro"
        >
          <AnimatedEchoLogo className="applogin-logo-intro-svg" />
        </div>
      )}
      <div className={`applogin-box ${introDone ? 'applogin-box--ready' : 'applogin-box--intro'}`}>
        <img ref={logoTargetRef} src={logo} alt="Echo" className="applogin-logo" />
        <div className="applogin-enter applogin-enter--heading">
          <h1 className="applogin-title">回声 Echo</h1>
          <p className="applogin-sub">
            {tab === 'login' ? '登录以继续你的知识之旅' : '创建账号，开启你的 AI 知识库'}
          </p>
        </div>
        <div className="applogin-enter applogin-enter--form">
          <Tabs
            activeKey={tab}
            onChange={setTab}
            centered
            items={[
              { key: 'login', label: '登录', children: renderForm(onLogin, '登录', true) },
              {
                key: 'register',
                label: '注册',
                children: renderForm(onRegister, '注册', false),
              },
            ]}
          />
        </div>
        <div className="applogin-foot applogin-enter applogin-enter--foot">个人 AI 知识库与记忆助手</div>
      </div>
    </div>
  )
}
