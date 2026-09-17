import type { Conversation } from '../lib/api'

interface Props {
  conversations: Conversation[]
  activeId: string | null
  onSelect: (id: string) => void
  onCreate: () => void
  onDelete: (id: string) => void
}

const dateFmt = new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })

export function ConversationList({ conversations, activeId, onSelect, onCreate, onDelete }: Props) {
  return (
    <nav className="rail" aria-label="Hội thoại">
      <div className="brand">
        <svg viewBox="0 0 32 32" aria-hidden width="28" height="28">
          <rect width="32" height="32" rx="7" fill="#0F2A3D" />
          <path d="M6 21c3 0 3-2 5-2s2 2 5 2 3-2 5-2 2 2 5 2" fill="none" stroke="#BFD7E3" strokeWidth="2" strokeLinecap="round" />
          <path d="M16 5v11M11 12l5-7 5 7" fill="none" stroke="#E0548F" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <div>
          <strong>Hải đồ hỏi đáp</strong>
          <span>AIS 10–12/09/2026</span>
        </div>
      </div>
      <button type="button" className="primary-button" onClick={onCreate}>
        Cuộc hỏi đáp mới
      </button>
      <ul className="conv-list">
        {conversations.length === 0 && <li className="conv-empty">Chưa có cuộc hỏi đáp nào.</li>}
        {conversations.map((c) => (
          <li key={c.id} className={c.id === activeId ? 'is-active' : ''}>
            <button type="button" className="conv-open" onClick={() => onSelect(c.id)} aria-current={c.id === activeId}>
              <span className="conv-title">{c.title}</span>
              <time dateTime={c.updated_at}>{dateFmt.format(new Date(c.updated_at))}</time>
            </button>
            <button
              type="button"
              className="icon-button conv-delete"
              onClick={() => onDelete(c.id)}
              aria-label={`Xoá cuộc hỏi đáp ${c.title}`}
            >
              ×
            </button>
          </li>
        ))}
      </ul>
    </nav>
  )
}
