import type { MapKind } from './api'

const GROUP_LABELS: Record<string, string> = {
  tanker: 'tàu chở dầu/hoá chất/khí',
  cargo: 'tàu hàng',
  fishing: 'tàu cá',
  tug: 'tàu kéo',
  passenger: 'tàu khách',
  high_speed: 'tàu cao tốc',
  pleasure: 'tàu du lịch',
  special: 'tàu công vụ',
  other: 'loại khác',
  unknown: 'chưa rõ loại',
}

const num = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 })

function day(ts: unknown): string {
  if (typeof ts !== 'string') return ''
  return ts.replace('T', ' ').replace(/:\d\dZ$/, ' UTC')
}

type Summary = Record<string, unknown> & {
  vessel?: { name?: string } | null
  filters?: { company?: string | null; ship_type_group?: string | null; start?: string; end?: string }
}

/** Tên và mô tả ngắn của một lớp bản đồ, sinh từ tóm tắt mà server gửi kèm. */
export function layerMeta(kind: MapKind, raw: Record<string, unknown>): { label: string; detail: string } {
  const s = raw as Summary
  const vessel = s.vessel?.name ?? ''
  switch (kind) {
    case 'position':
      return { label: `Vị trí ${vessel}`, detail: day(s.requested_ts) }
    case 'track':
      return {
        label: `Hành trình ${vessel}`,
        detail: `${num.format(Number(s.distance_nm ?? 0))} hải lý, ${s.point_count ?? 0} điểm`,
      }
    case 'gaps':
      return {
        label: vessel ? `Mất tín hiệu của ${vessel}` : 'Các lần mất tín hiệu',
        detail: `${s.count ?? 0} lần hiển thị`,
      }
    case 'tracks': {
      const f = s.filters ?? {}
      const parts = [f.company, f.ship_type_group ? GROUP_LABELS[f.ship_type_group] ?? f.ship_type_group : null].filter(Boolean)
      return {
        label: `Hành trình ${parts.length ? parts.join(', ') : 'mọi tàu'}`,
        detail: `${s.vessels_with_data ?? 0} tàu, ${num.format(Number(s.total_points ?? 0))} điểm, ${(f.start ?? '').slice(5, 10)} đến ${(f.end ?? '').slice(5, 10)}`,
      }
    }
  }
}
