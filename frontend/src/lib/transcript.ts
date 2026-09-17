import type { IconName } from '../components/Icon'
import type { Evidence, GuardrailNote, StoredMessage, ToolResultEvent, Verification } from './api'

export interface ToolStep {
  id: string
  name: string
  args: Record<string, unknown> | string
  ok?: boolean
  summary?: Record<string, unknown>
  evidenceId?: string
}

export interface Turn {
  key: string
  question: string
  steps: ToolStep[]
  answer: string
  mapIds: string[]
  evidence: Evidence[]
  verification?: Verification
  guardrails: GuardrailNote[]
  error?: string
  interrupted?: boolean
  pending?: boolean
  memory?: { window: number[]; summary: boolean; recalled: { turn: number; score: number }[] }
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

/** Gom tin nhắn đã lưu thành các lượt hiển thị (câu hỏi, các bước tool, lớp bản đồ, câu trả lời). */
export function buildTurns(messages: StoredMessage[]): Turn[] {
  const turns = new Map<number, Turn>()
  for (const m of messages) {
    let turn = turns.get(m.turn_no)
    if (!turn) {
      turn = { key: `t${m.turn_no}`, question: '', steps: [], answer: '', mapIds: [], evidence: [], guardrails: [] }
      turns.set(m.turn_no, turn)
    }
    if (m.role === 'user') {
      turn.question = m.content
    } else if (m.role === 'assistant') {
      for (const call of m.tool_calls ?? []) {
        turn.steps.push({ id: call.id, name: call.function.name, args: parseArgs(call.function.arguments) })
      }
      if (m.content) turn.answer += m.content
      if (m.meta?.data_ids) turn.mapIds.push(...m.meta.data_ids)
      if (m.meta?.evidence) {
        turn.evidence.push(...m.meta.evidence)
        // Chứng cứ theo đúng thứ tự các lần gọi tool của lượt
        turn.steps.forEach((step, i) => {
          step.evidenceId = turn!.evidence[i]?.id
        })
      }
      if (m.meta?.verification) turn.verification = m.meta.verification
      if (m.meta?.guardrail) turn.guardrails.push(...m.meta.guardrail)
      if (m.meta?.error) turn.error = `Không hoàn tất câu trả lời (${m.meta.error}).`
      if (m.meta?.interrupted) turn.interrupted = true
    } else if (m.role === 'tool') {
      const step = turn.steps.find((s) => s.id === m.tool_call_id)
      if (step) Object.assign(step, summarizeToolContent(m.content))
    }
  }
  return [...turns.entries()].sort((a, b) => a[0] - b[0]).map(([, t]) => t)
}

const TOOLS: Record<string, { label: string; icon: IconName }> = {
  search_vessels: { label: 'Tìm tàu', icon: 'search' },
  list_vessels: { label: 'Liệt kê tàu', icon: 'database' },
  get_vessel_details: { label: 'Tra hồ sơ tàu', icon: 'ship' },
  find_company_vessels: { label: 'Tra đội tàu của công ty', icon: 'company' },
  get_position_at: { label: 'Tra vị trí theo thời điểm', icon: 'pin' },
  get_last_position: { label: 'Tra vị trí cuối cùng', icon: 'pin' },
  get_track: { label: 'Dựng hành trình', icon: 'route' },
  get_dark_gaps: { label: 'Tra các lần mất tín hiệu', icon: 'signalOff' },
  get_multi_tracks: { label: 'Dựng nhiều hành trình', icon: 'fleet' },
  search_knowledge: { label: 'Tra kho tri thức', icon: 'book' },
}

export function toolMeta(name: string): { label: string; icon: IconName } {
  return TOOLS[name] ?? { label: name, icon: 'compass' }
}

const ARG_LABELS: Record<string, string> = {
  vessel: 'Tàu',
  query: 'Tìm',
  company_name: 'Công ty',
  role: 'Vai trò',
  ship_type_group: 'Loại tàu',
  timestamp: 'Lúc',
  start: 'Từ',
  end: 'Đến',
  order_by: 'Sắp xếp',
  exclude_vessel: 'Trừ tàu',
  limit: 'Số lượng',
  offset: 'Bỏ qua',
  flag: 'Cờ',
  name_contains: 'Tên chứa',
}

const VALUE_LABELS: Record<string, string> = {
  registered_owner: 'chủ sở hữu đăng ký',
  beneficial_owner: 'chủ sở hữu hưởng lợi',
  operator: 'nhà khai thác',
  commercial_manager: 'quản lý thương mại',
  technical_manager: 'quản lý kỹ thuật',
  ism_manager: 'quản lý ISM',
  tanker: 'tàu dầu/hoá chất/khí',
  cargo: 'tàu hàng',
  fishing: 'tàu cá',
  tug: 'tàu kéo',
  passenger: 'tàu khách',
  duration: 'lâu nhất',
  distance: 'xa nhất',
  start: 'theo thời gian',
  name: 'theo tên',
  dwt: 'trọng tải lớn nhất',
  length: 'dài nhất',
  year_built: 'mới đóng nhất',
  special: 'tàu chuyên dụng',
  other: 'loại khác',
}

const ISO = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/

function formatValue(v: unknown): string {
  const text = String(v)
  const m = ISO.exec(text)
  if (m) return m[4] ? `${m[3]}/${m[2]} ${m[4]}:${m[5]}` : `${m[3]}/${m[2]}`
  return VALUE_LABELS[text] ?? text
}

/** Tham số tool dạng nhãn tiếng Việt để hiển thị thành chip. */
export function argChips(args: ToolStep['args']): { label: string; value: string }[] {
  if (typeof args === 'string') return [{ label: 'Tham số', value: args }]
  return Object.entries(args)
    .filter(([k, v]) => v !== null && v !== undefined && v !== '' && k in ARG_LABELS && !(k === 'offset' && v === 0))
    .map(([k, v]) => ({ label: ARG_LABELS[k], value: formatValue(v) }))
}

const CITATION = /\[(E\d+(?:\s*,\s*E\d+)*)\]/g

/** Đổi mã chứng cứ [E1, E2] trong câu trả lời thành liên kết nội bộ để hiển thị thành chip. */
export function linkCitations(markdown: string): string {
  return markdown.replace(CITATION, (_, group: string) =>
    group
      .split(',')
      .map((id) => id.trim())
      .map((id) => `[${id}](#evidence-${id})`)
      .join(' '),
  )
}
