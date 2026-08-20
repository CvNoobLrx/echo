import client from './client'

interface Wrapped<T> { code: number; message: string; data: T }

export type DeliveryStatus = 'queued' | 'generating' | 'sent' | 'failed'

export interface NewsDelivery {
  id: string
  trigger: 'scheduled' | 'manual'
  status: DeliveryStatus
  recipient_email: string
  subject: string | null
  error_message: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string | null
}

export interface NewsSettings {
  enabled: boolean
  topics: string[]
  email: string | null
  schedule: string
  readiness: { smtp: boolean; chat_model: boolean; web_search: boolean }
  smtp: {
    configured: boolean
    provider: 'qq' | '163' | 'gmail' | 'outlook' | null
    sender_email: string | null
    from_name: string | null
  }
  latest_delivery: NewsDelivery | null
}

export interface NewsSmtpInput {
  provider: 'qq' | '163' | 'gmail' | 'outlook'
  sender_email: string
  password?: string
  from_name: string
}

export const newsApi = {
  getSettings: () => client.get<unknown, Wrapped<NewsSettings>>('/news-subscription'),
  updateSettings: (body: { enabled: boolean; topics: string[] }) =>
    client.put<unknown, Wrapped<NewsSettings>>('/news-subscription', body),
  updateSmtp: (body: NewsSmtpInput) =>
    client.put<unknown, Wrapped<NewsSettings>>('/news-subscription/smtp', body),
  testEmail: () => client.post<unknown, Wrapped<null>>('/news-subscription/test-email'),
  sendNow: () => client.post<unknown, Wrapped<{ delivery_id: string }>>('/news-subscription/send-now'),
  getDelivery: (id: string) =>
    client.get<unknown, Wrapped<NewsDelivery>>(`/news-deliveries/${id}`),
}
