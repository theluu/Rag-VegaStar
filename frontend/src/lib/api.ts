import type { FeatureCollection } from 'geojson'
import { SseParser } from './sse'

export const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''

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
  meta: { data_ids?: string[]; error?: string; interrupted?: boolean } | null
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
  onError: (e: { code: string; message: string }) => void
  onDone: () => void
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
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
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ message }),
    signal,
  })
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
