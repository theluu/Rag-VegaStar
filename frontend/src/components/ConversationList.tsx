import { useMemo, useState } from 'react'
import type { Conversation } from '../lib/api'
import { Icon } from './Icon'

export type AppView = 'chat' | 'stats'

interface Props {
  view: AppView
  onViewChange: (view: AppView) => void
  conversations: Conversation[]
  activeId: string | null
  apiOnline: boolean
  onSelect: (id: string) => void
  onCreate: () => void
  onDelete: (id: string) => void
}

const timeFmt = new Intl.DateTimeFormat('vi-VN', { hour: '2-digit', minute: '2-digit' })
const dayFmt = new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' })

function dayLabel(d: Date): string {
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  if (d.toDateString() === today.toDateString()) return 'Hôm nay'
  if (d.toDateString() === yesterday.toDateString()) return 'Hôm qua'
  return dayFmt.format(d)
}

export function ConversationList({ view, onViewChange, conversations, activeId, apiOnline, onSelect, onCreate, onDelete }: Props) {
  const [query, setQuery] = useState('')
  const [confirming, setConfirming] = useState<string | null>(null)

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase()
    const out = new Map<string, Conversation[]>()
    for (const c of conversations) {
      if (q && !c.title.toLowerCase().includes(q)) continue
      const label = dayLabel(new Date(c.updated_at))
      out.set(label, [...(out.get(label) ?? []), c])
    }
    return [...out.entries()]
  }, [conversations, query])

  return (
    <nav className="rail" aria-label="Hội thoại">
      <div className="brand">
        <svg viewBox="0 0 40 40" width="38" height="38" aria-hidden>
          <rect width="40" height="40" rx="10" fill="#B3246B" />
          <circle cx="20" cy="20" r="11" fill="none" stroke="#fff" strokeOpacity=".35" strokeWidth="1.5" />
          <path d="M20 7v26M7 20h26" stroke="#fff" strokeOpacity=".35" strokeWidth="1.2" />
          <path d="M20 11l4.5 9L20 29l-4.5-9z" fill="#fff" />
        </svg>
        <div>
          <strong>Hải đồ hỏi đáp</strong>
          <span>Tra cứu tàu biển bằng AI</span>
        </div>
      </div>

      <div className="view-switch" role="tablist" aria-label="Chế độ xem">
        <button type="button" role="tab" aria-selected={view === 'chat'} onClick={() => onViewChange('chat')}>
          <Icon name="chat" size={16} />
          Hỏi đáp
        </button>
        <button type="button" role="tab" aria-selected={view === 'stats'} onClick={() => onViewChange('stats')}>
          <Icon name="chart" size={16} />
          Thống kê
        </button>
      </div>

      <button type="button" className="new-button" onClick={onCreate}>
        <Icon name="plus" size={18} />
        Cuộc hỏi đáp mới
      </button>

      <label className="rail-search">
        <Icon name="search" size={15} />
        <span className="visually-hidden">Tìm cuộc hỏi đáp</span>
        <input type="search" placeholder="Tìm cuộc hỏi đáp" value={query} onChange={(e) => setQuery(e.target.value)} />
      </label>

      <div className="conv-scroll">
        {conversations.length === 0 && <p className="rail-empty">Chưa có cuộc hỏi đáp nào. Bắt đầu bằng một câu hỏi.</p>}
        {conversations.length > 0 && groups.length === 0 && <p className="rail-empty">Không có cuộc hỏi đáp nào khớp.</p>}
        {groups.map(([label, items]) => (
          <section key={label}>
            <h2 className="conv-day">{label}</h2>
            <ul className="conv-list">
              {items.map((c) => {
                const active = c.id === activeId
                const asking = confirming === c.id
                return (
                  <li key={c.id} className={active && view === 'chat' ? 'is-active' : ''}>
                    <button type="button" className="conv-open" onClick={() => onSelect(c.id)} aria-current={active}>
                      <span className="conv-title">{c.title}</span>
                      <span className="conv-meta">
                        {timeFmt.format(new Date(c.updated_at))}, {c.turn_count} lượt hỏi
                      </span>
                    </button>
                    {asking ? (
                      <span className="conv-confirm">
                        <button type="button" onClick={() => { onDelete(c.id); setConfirming(null) }}>
                          Xoá
                        </button>
                        <button type="button" onClick={() => setConfirming(null)}>
                          Giữ
                        </button>
                      </span>
                    ) : (
                      <button
                        type="button"
                        className="conv-delete"
                        onClick={() => setConfirming(c.id)}
                        aria-label={`Xoá cuộc hỏi đáp ${c.title}`}
                      >
                        <Icon name="trash" size={15} />
                      </button>
                    )}
                  </li>
                )
              })}
            </ul>
          </section>
        ))}
      </div>

      <footer className="rail-foot">
        <span className={`status-dot ${apiOnline ? 'online' : 'offline'}`} aria-hidden />
        {apiOnline ? 'Đã kết nối dữ liệu AIS 10–12/09/2026' : 'Chưa kết nối được API'}
      </footer>
    </nav>
  )
}
