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

export type StatsRange = '24h' | '7d' | '30d' | 'all'
export type TurnOutcome = 'ok' | 'blocked' | 'error' | 'cancelled'

export interface ToolStat {
  name: string
  calls: number
  ok: number
  success_rate: number | null
  measured: number
  cache_hit_rate: number | null
  ms_p50: number | null
  ms_p95: number | null
}

export interface RecentTurn {
  id: number
  conversation_id: string
  title: string
  turn_no: number
  created_at: string
  outcome: TurnOutcome
  question: string | null
  tools: string[]
  prompt_tokens: number | null
  completion_tokens: number | null
  ttft_s: number | null
  duration_s: number | null
  grounded: boolean | null
  evidence_count: number
  guardrail_kind: string | null
  cost_usd: number
}

export interface EvalSummary {
  generated_at: string
  cases: number
  passed: number
  pass_rate: number
  cost_usd: number | null
  first_token_p50: number | null
  total_p50: number | null
  categories: { name: string; cases: number; passed: number }[]
  failed_checks: Record<string, number>
}

export interface Stats {
  generated_at: string
  range: StatsRange
  since: string | null
  timezone: string
  overview: {
    turns: number
    conversations: number
    outcomes: Record<TurnOutcome, number>
    success_rate: number | null
    prompt_tokens: number
    completion_tokens: number
    cost_usd: number
    cost_per_turn_usd: number | null
    tool_calls: number
    tool_calls_per_turn: number | null
    first_turn_at: string | null
    last_turn_at: string | null
  }
  latency: {
    measured_turns: number
    ttft_p50: number | null
    ttft_p95: number | null
    duration_p50: number | null
    duration_p95: number | null
  }
  daily: { day: string; turns: number; blocked: number; errors: number; cost_usd: number }[]
  tools: ToolStat[]
  cache: { hit_rate: number | null; hits: number; lookups: number; entries: number | null; max_entries: number }
  quality: {
    verified_answers: number
    grounded_answers: number
    grounded_rate: number | null
    numbers_checked: number
    answers_with_evidence: number
    cited_answers: number
    citation_rate: number | null
    auto_cited: number
  }
  guardrails: { stage: 'input' | 'output'; action: 'block' | 'warn' | 'redact'; kind: string; count: number }[]
  rag: {
    knowledge_searches: number
    knowledge_docs: number
    knowledge_chunks: number
    memory_chunks: number
    summarized_conversations: number
  }
  recent_turns: RecentTurn[]
  data: {
    vessels: number
    positions: number
    positions_from: string | null
    positions_to: string | null
    vessels_with_positions: number
    dark_gaps: number
    ownership_rows: number
    companies: number
    knowledge_chunks: number
    knowledge_docs: number
    conversations_total: number
    map_layers: number
    ship_type_groups: { name: string; count: number }[]
  }
  evaluation: EvalSummary | null
  runtime: {
    model: string
    embedding_model: string
    memory_window_turns: number
    max_tool_iterations: number
    moderation_enabled: boolean
    grounding_enabled: boolean
    auth_required: boolean
    rate_limit_chat_per_minute: number
    price_input_per_m: number
    price_output_per_m: number
    started_at: string | null
  }
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
  getStats: (range: StatsRange, signal?: AbortSignal) => request<Stats>(`/stats?range=${range}`, { signal }),
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
