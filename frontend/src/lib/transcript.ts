import type { StoredMessage, ToolResultEvent } from './api'

export interface ToolStep {
  id: string
  name: string
  args: Record<string, unknown> | string
  ok?: boolean
  summary?: Record<string, unknown>
}

export interface Turn {
  key: string
  question: string
  steps: ToolStep[]
  answer: string
  error?: string
  interrupted?: boolean
  pending?: boolean
  memory?: { window: number[]; summary: boolean; recalled: number[] }
}

function parseArgs(raw: string): Record<string, unknown> | string {
  try {
    return JSON.parse(raw) as Record<string, unknown>
  } catch {
    return raw
  }
}

function summarizeToolContent(content: string): Pick<ToolResultEvent, 'ok' | 'summary'> {
  try {
    const parsed = JSON.parse(content) as Record<string, unknown>
    if ('error' in parsed) return { ok: false, summary: { error: parsed.error } }
    const keep = ['status', 'count', 'vessel_count', 'total_matching', 'point_count', 'distance_nm', 'matched_vessels', 'method']
    return { ok: true, summary: Object.fromEntries(keep.filter((k) => k in parsed).map((k) => [k, parsed[k]])) }
  } catch {
    return { ok: true, summary: {} }
  }
}

/** Gom tin nhắn đã lưu thành các lượt hiển thị (câu hỏi, các bước tool, câu trả lời). */
export function buildTurns(messages: StoredMessage[]): Turn[] {
  const turns = new Map<number, Turn>()
  for (const m of messages) {
    let turn = turns.get(m.turn_no)
    if (!turn) {
      turn = { key: `t${m.turn_no}`, question: '', steps: [], answer: '' }
      turns.set(m.turn_no, turn)
    }
    if (m.role === 'user') {
      turn.question = m.content
    } else if (m.role === 'assistant') {
      for (const call of m.tool_calls ?? []) {
        turn.steps.push({ id: call.id, name: call.function.name, args: parseArgs(call.function.arguments) })
      }
      if (m.content) turn.answer += m.content
      if (m.meta?.error) turn.error = `Không hoàn tất câu trả lời (${m.meta.error}).`
      if (m.meta?.interrupted) turn.interrupted = true
    } else if (m.role === 'tool') {
      const step = turn.steps.find((s) => s.id === m.tool_call_id)
      if (step) Object.assign(step, summarizeToolContent(m.content))
    }
  }
  return [...turns.entries()].sort((a, b) => a[0] - b[0]).map(([, t]) => t)
}

const TOOL_LABELS: Record<string, string> = {
  search_vessels: 'Tìm tàu',
  get_vessel_details: 'Tra hồ sơ tàu',
  find_company_vessels: 'Tra đội tàu của công ty',
  get_position_at: 'Tra vị trí theo thời điểm',
  get_last_position: 'Tra vị trí cuối cùng',
  get_track: 'Dựng hành trình',
  get_dark_gaps: 'Tra các lần mất tín hiệu',
  get_multi_tracks: 'Dựng nhiều hành trình',
}

export function toolLabel(name: string): string {
  return TOOL_LABELS[name] ?? name
}

/** Mô tả ngắn tham số tool để hiển thị trong nhật ký. */
export function describeArgs(args: ToolStep['args']): string {
  if (typeof args === 'string') return args
  return Object.entries(args)
    .filter(([, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => `${k}: ${String(v)}`)
    .join(', ')
}
