import type { Evidence, Verification } from '../lib/api'
import { argChips, toolMeta } from '../lib/transcript'
import { Icon } from './Icon'

const SOURCE_LABELS: Record<string, string> = {
  vessels: 'Đăng kiểm tàu',
  ownership: 'Chủ sở hữu',
  ais_positions: 'Vị trí AIS',
  dark_gaps: 'Mất tín hiệu',
}

export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? `Tài liệu ${source.replace(/\.md$/, '')}`
}

export function VerificationBadge({ verification, evidenceCount }: { verification?: Verification; evidenceCount: number }) {
  if (!verification) return null
  const { numbers_checked: checked, ungrounded_numbers: bad, unknown_citations: unknown } = verification
  if (bad.length || unknown.length) {
    const parts = []
    if (bad.length) parts.push(`${bad.length} số chưa khớp dữ liệu (${bad.join(', ')})`)
    if (unknown.length) parts.push(`mã chứng cứ không tồn tại (${unknown.join(', ')})`)
    return (
      <span className="verify verify-warn">
        <Icon name="alert" size={14} /> Cần kiểm tra: {parts.join('; ')}
      </span>
    )
  }
  if (checked > 0) {
    return (
      <span className="verify verify-ok">
        <Icon name="shield" size={14} /> Đã đối chiếu {checked} số liệu với dữ liệu truy vấn
      </span>
    )
  }
  if (evidenceCount > 0) {
    return (
      <span className="verify verify-ok">
        <Icon name="shield" size={14} /> Dựa trên {evidenceCount} chứng cứ
      </span>
    )
  }
  return null
}

function EvidenceCard({ ev, onShowLayer }: { ev: Evidence; onShowLayer: (id: string) => void }) {
  const meta = toolMeta(ev.tool)
  return (
    <li className={`evidence-card${ev.ok ? '' : ' is-failed'}`} id={`evidence-card-${ev.id}`}>
      <header>
        <span className="evidence-id">{ev.id}</span>
        <span className="evidence-icon">
          <Icon name={meta.icon} size={14} />
        </span>
        <strong>{ev.label}</strong>
      </header>
      <div className="evidence-meta">
        {ev.sources.map((s) => (
          <span key={s} className="source-chip">
            <Icon name={s.endsWith('.md') ? 'book' : 'database'} size={12} /> {sourceLabel(s)}
          </span>
        ))}
        {argChips(ev.query).map((c) => (
          <span key={c.label + c.value} className="chip">
            <span className="chip-label">{c.label}</span> {c.value}
          </span>
        ))}
      </div>
      {ev.facts.length > 0 && (
        <dl className="evidence-facts">
          {ev.facts.map((f, i) => (
            <div key={`${f.label}-${i}`}>
              <dt>{f.label}</dt>
              <dd>{f.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {ev.data_ids.length > 0 && (
        <button type="button" className="link-button" onClick={() => onShowLayer(ev.data_ids[0])}>
          <Icon name="focus" size={13} /> Xem trên bản đồ
        </button>
      )}
    </li>
  )
}

interface Props {
  evidence: Evidence[]
  verification?: Verification
  turnKey: string
  onShowLayer: (id: string) => void
}

export function EvidencePanel({ evidence, verification, turnKey, onShowLayer }: Props) {
  if (evidence.length === 0 && !verification) return null
  return (
    <div className="evidence">
      <div className="evidence-bar">
        <VerificationBadge verification={verification} evidenceCount={evidence.length} />
      </div>
      {evidence.length > 0 && (
        <details className="evidence-details" id={`evidence-${turnKey}`}>
          <summary>
            <Icon name="chevron" size={14} className="evidence-chevron" />
            Chứng cứ ({evidence.length}): {evidence.map((e) => e.id).join(', ')}
          </summary>
          <ul>
            {evidence.map((ev) => (
              <EvidenceCard key={ev.id} ev={ev} onShowLayer={onShowLayer} />
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

/** Mở và cuộn tới thẻ chứng cứ (có thể nằm ở lượt trước). */
export function revealEvidence(id: string): boolean {
  const card = document.getElementById(`evidence-card-${id}`)
  if (!card) return false
  const details = card.closest('details')
  if (details) details.open = true
  card.scrollIntoView({ behavior: 'smooth', block: 'center' })
  card.classList.remove('is-flash')
  void card.offsetWidth
  card.classList.add('is-flash')
  return true
}
