// Định dạng và chuẩn hoá số liệu cho trang Thống kê
import type { Stats, StatsRange, TurnOutcome } from './api'

const intFmt = new Intl.NumberFormat('vi-VN')
const compactFmt = new Intl.NumberFormat('vi-VN', { notation: 'compact', maximumFractionDigits: 1 })
const dayFmt = new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit' })
const dateTimeFmt = new Intl.DateTimeFormat('vi-VN', {
  day: '2-digit',
  month: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})

export const RANGES: { value: StatsRange; label: string }[] = [
  { value: '24h', label: '24 giờ' },
  { value: '7d', label: '7 ngày' },
  { value: '30d', label: '30 ngày' },
  { value: 'all', label: 'Toàn bộ' },
]

export const OUTCOMES: { key: TurnOutcome; label: string }[] = [
  { key: 'ok', label: 'Trả lời xong' },
  { key: 'blocked', label: 'Bị guardrail chặn' },
  { key: 'error', label: 'Lỗi' },
  { key: 'cancelled', label: 'Người dùng dừng' },
]

const GUARD_KINDS: Record<string, string> = {
  prompt_injection: 'Prompt injection',
  prompt_injection_suspected: 'Nghi thay đổi chỉ dẫn',
  moderation: 'Nội dung vi phạm',
  moderation_unavailable: 'Kiểm duyệt không sẵn sàng',
  secret: 'Chuỗi giống bí mật',
  system_prompt_leak: 'Lặp lại chỉ dẫn nội bộ',
  ungrounded_numbers: 'Số liệu không có nguồn',
  unknown_citations: 'Mã chứng cứ không tồn tại',
}

const GUARD_ACTIONS: Record<string, string> = { block: 'Chặn', warn: 'Cảnh báo', redact: 'Che' }

const SHIP_GROUPS: Record<string, string> = {
  cargo: 'Tàu hàng',
  tanker: 'Tàu dầu, hoá chất, khí',
  fishing: 'Tàu cá',
  tug: 'Tàu kéo',
  passenger: 'Tàu khách',
  high_speed: 'Tàu cao tốc',
  pleasure: 'Du thuyền, tàu buồm',
  special: 'Tàu chuyên dụng',
  other: 'Loại khác',
  unknown: 'Chưa rõ loại',
}

const EVAL_CATEGORIES: Record<string, string> = {
  knowledge: 'Kiến thức (RAG)',
  multi_turn: 'Hội thoại nhiều lượt',
  red_team: 'Red-team',
  out_of_scope: 'Ngoài phạm vi',
  missing_data: 'Thiếu dữ liệu',
  vessel_info: 'Hồ sơ tàu',
  identifier_lookup: 'Tra MMSI, IMO, hô hiệu',
  ownership: 'Chủ sở hữu',
  position_at: 'Vị trí theo thời điểm',
  track: 'Hành trình',
  last_position: 'Vị trí cuối',
  dark_gaps: 'Mất tín hiệu AIS',
  company_fleet: 'Đội tàu công ty',
  multi_tracks: 'Nhiều hành trình',
  vessel_list: 'Đếm, liệt kê tàu',
}

export const guardKindLabel = (kind: string) => GUARD_KINDS[kind] ?? kind
export const guardActionLabel = (action: string) => GUARD_ACTIONS[action] ?? action
export const shipGroupLabel = (name: string) => SHIP_GROUPS[name] ?? name
export const evalCategoryLabel = (name: string) => EVAL_CATEGORIES[name] ?? name

export const fmtInt = (n: number | null | undefined) => (n == null ? '—' : intFmt.format(n))
export const fmtCompact = (n: number | null | undefined) => (n == null ? '—' : compactFmt.format(n))

export function fmtPercent(ratio: number | null | undefined, digits = 0): string {
  if (ratio == null) return '—'
  return `${(ratio * 100).toLocaleString('vi-VN', { maximumFractionDigits: digits })}%`
}

/** Chi phí nhỏ cần nhiều chữ số hơn để không hiện thành 0. */
export function fmtUsd(value: number | null | undefined): string {
  if (value == null) return '—'
  if (value === 0) return '$0'
  const digits = value >= 1 ? 2 : value >= 0.01 ? 3 : 4
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`
}

export function fmtSeconds(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${value.toLocaleString('vi-VN', { maximumFractionDigits: value < 10 ? 1 : 0 })} s`
}

export function fmtMs(value: number | null | undefined): string {
  if (value == null) return '—'
  if (value >= 1000) return fmtSeconds(value / 1000)
  return `${value.toLocaleString('vi-VN', { maximumFractionDigits: value < 10 ? 1 : 0 })} ms`
}

export const fmtDay = (iso: string) => dayFmt.format(new Date(`${iso}T00:00:00`))
export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const p = Object.fromEntries(dateTimeFmt.formatToParts(new Date(iso)).map((x) => [x.type, x.value]))
  return `${p.day}/${p.month} ${p.hour}:${p.minute}`
}

export function fmtUptime(startedAt: string | null, now = Date.now()): string {
  if (!startedAt) return '—'
  const minutes = Math.max(0, Math.floor((now - new Date(startedAt).getTime()) / 60000))
  if (minutes < 60) return `${minutes} phút`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} giờ ${minutes % 60} phút`
  return `${Math.floor(hours / 24)} ngày ${hours % 24} giờ`
}

export interface DayPoint {
  day: string
  turns: number
  blocked: number
  errors: number
  cost_usd: number
}

/**
 * Chuỗi ngày liên tục cho biểu đồ: ngày không có lượt nào vẫn hiện cột 0.
 * Với "Toàn bộ", bắt đầu từ ngày đầu tiên có dữ liệu.
 */
export function fillDays(daily: Stats['daily'], range: StatsRange, today: string): DayPoint[] {
  const span = range === '24h' ? 1 : range === '7d' ? 7 : range === '30d' ? 30 : null
  const byDay = new Map(daily.map((d) => [d.day, d]))
  const end = new Date(`${today}T00:00:00Z`)
  let start: Date
  if (span != null) {
    start = new Date(end)
    start.setUTCDate(end.getUTCDate() - (span - 1))
  } else if (daily.length) {
    start = new Date(`${daily[0].day}T00:00:00Z`)
  } else {
    start = end
  }
  const out: DayPoint[] = []
  for (const d = new Date(start); d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
    const key = d.toISOString().slice(0, 10)
    const hit = byDay.get(key)
    out.push(hit ?? { day: key, turns: 0, blocked: 0, errors: 0, cost_usd: 0 })
  }
  return out
}

/** Ngày hôm nay (YYYY-MM-DD) theo múi giờ server dùng để gom số liệu. */
export function todayIn(timeZone: string, now = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(now)
}

/** Bước chia trục tròn (1, 2, 5 × 10^n) để nhãn trục dễ đọc. */
export function niceMax(value: number, ticks = 4): number {
  if (value <= 0) return ticks
  const raw = value / ticks
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag
  return step * ticks
}
