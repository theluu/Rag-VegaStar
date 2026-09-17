import type { FeatureCollection } from 'geojson'
import { SseParser } from './sse'

export const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''
// Chỉ dùng khi API bật API_KEYS cho môi trường demo nội bộ; production nên đặt sau lớp xác thực phía server
const API_KEY = import.meta.env.VITE_API_KEY as string | undefined

function authHeaders(): Record<string, string> {
  return API_KEY ? { 'X-API-Key': API_KEY } : {}
}

export interface EvidenceFact {
  label: string
  value: string
}

export interface Evidence {
  id: string
  tool: string
  label: string
  ok: boolean
  query: Record<string, unknown> | string
  sources: string[]
  facts: EvidenceFact[]
  data_ids: string[]
}

export interface Verification {
  numbers_checked: number
  ungrounded_numbers: string[]
  citations: string[]
  unknown_citations: string[]
  evidence_count: number
  grounded: boolean
}

export interface GuardrailNote {
  stage: 'input' | 'output'
  action: 'block' | 'warn' | 'redact'
  kind: string
  message?: string
  numbers?: string[]
}

export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
  turn_count: number
}

export interface StoredToolCall {
  id: string
  function: { name: string; arguments: string }
}

export interface StoredMessage {
  id: number
  turn_no: number
  role: 'user' | 'assistant' | 'tool'
  content: string
  tool_calls: StoredToolCall[] | null
  tool_call_id: string | null
  tool_name: string | null
  meta: {
    data_ids?: string[]
    error?: string
    interrupted?: boolean
    evidence?: Evidence[]
    verification?: Verification
    guardrail?: GuardrailNote[]
  } | null
  created_at: string
}

export type MapKind = 'position' | 'track' | 'gaps' | 'tracks'

export interface MapDataRef {
  id: string
  kind: MapKind
  summary: Record<string, unknown>
  bbox: [number, number, number, number] | null
}

export interface MapData extends MapDataRef {
  geojson: FeatureCollection
}

export interface ToolCallEvent {
  id: string
  name: string
  args: Record<string, unknown> | string
}

export interface ToolResultEvent {
  id: string
  name: string
  ok: boolean
  summary: Record<string, unknown>
  evidence_id?: string
}

export interface DataEvent {
  data_id: string
  kind: MapKind
  bbox: [number, number, number, number] | null
  summary: Record<string, unknown>
  tool_call_id: string
}

export interface MemoryEvent {
  window_turns: number[]
  summary_used: boolean
  retrieved: { turn_no: number; score: number; text: string }[]
}

export interface StreamHandlers {
  onToken: (text: string) => void
  onToolCall: (e: ToolCallEvent) => void
  onToolResult: (e: ToolResultEvent) => void
  onData: (e: DataEvent) => void
  onMemory: (e: MemoryEvent) => void
  onEvidence: (e: Evidence) => void
  onVerification: (e: Verification) => void
  onGuardrail: (e: GuardrailNote) => void
  onError: (e: { code: string; message: string }) => void
  onDone: () => void
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(init?.headers ?? {}) },
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${body.slice(0, 200)}`)
  }
  return (res.status === 204 ? undefined : await res.json()) as T
}

export const api = {
  listConversations: () => request<Conversation[]>('/conversations'),
  createConversation: () => request<Conversation>('/conversations', { method: 'POST', body: '{}' }),
  deleteConversation: (id: string) => request<void>(`/conversations/${id}`, { method: 'DELETE' }),
  listMessages: (id: string) => request<StoredMessage[]>(`/conversations/${id}/messages`),
  listMapData: (id: string) => request<MapDataRef[]>(`/conversations/${id}/map-data`),
  getMapData: (dataId: string) => request<MapData>(`/map-data/${dataId}`),
}

/** Gửi câu hỏi và đọc stream SSE qua fetch (EventSource không hỗ trợ POST). */
export async function streamChat(
  conversationId: string,
  message: string,
  handlers: StreamHandlers,
  signal: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_BASE}/conversations/${conversationId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', ...authHeaders() },
    body: JSON.stringify({ message }),
    signal,
  })
  if (res.status === 429) {
    throw new Error('Bạn hỏi hơi nhanh, vui lòng đợi vài giây rồi thử lại.')
  }
  if (res.status === 401) {
    throw new Error('API yêu cầu khoá truy cập (VITE_API_KEY).')
  }
  if (!res.ok || !res.body) {
    throw new Error(`Không gửi được câu hỏi (${res.status})`)
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
  const parser = new SseParser()
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    for (const { event, data } of parser.push(value)) {
      switch (event) {
        case 'token':
          handlers.onToken((data as { text: string }).text)
          break
        case 'tool_call':
          handlers.onToolCall(data as ToolCallEvent)
          break
        case 'tool_result':
          handlers.onToolResult(data as ToolResultEvent)
          break
        case 'data':
          handlers.onData(data as DataEvent)
          break
        case 'memory':
          handlers.onMemory(data as MemoryEvent)
          break
        case 'evidence':
          handlers.onEvidence(data as Evidence)
          break
        case 'verification':
          handlers.onVerification(data as Verification)
          break
        case 'guardrail':
          handlers.onGuardrail(data as GuardrailNote)
          break
        case 'error':
          handlers.onError(data as { code: string; message: string })
          break
        case 'done':
          handlers.onDone()
          break
      }
    }
  }
}
