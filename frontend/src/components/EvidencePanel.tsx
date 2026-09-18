import type { Evidence, SecondOpinion, Verification } from '../lib/api'
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

const VERDICT_TEXT: Record<string, string> = {
  ok: 'AI kiểm chứng độc lập đồng ý với câu trả lời',
  sai: 'AI kiểm chứng thấy số liệu chưa khớp',
  thieu: 'AI kiểm chứng thấy còn thiếu ý',
  khong_ro: 'AI kiểm chứng chưa kết luận được',
}

function SecondOpinionNote({ opinion }: { opinion: SecondOpinion }) {
  return (
    <span className={`verify ${opinion.agrees ? 'verify-second' : 'verify-warn'}`} title={`Model: ${opinion.model}`}>
      <Icon name={opinion.agrees ? 'check' : 'alert'} size={14} />
      {VERDICT_TEXT[opinion.verdict] ?? opinion.verdict}
      {opinion.issues.length > 0 && `: ${opinion.issues.join('; ')}`}
    </span>
  )
}

export function VerificationBadge({ verification, evidenceCount }: { verification?: Verification; evidenceCount: number }) {
  if (!verification) return null
  const { numbers_checked: checked, ungrounded_numbers: bad, unknown_citations: unknown } = verification
  const second = verification.second_opinion
  if (bad.length || unknown.length) {
    const parts = []
    if (bad.length) parts.push(`${bad.length} số chưa khớp dữ liệu (${bad.join(', ')})`)
    if (unknown.length) parts.push(`mã chứng cứ không tồn tại (${unknown.join(', ')})`)
    return (
      <>
        <span className="verify verify-warn">
          <Icon name="alert" size={14} /> Cần kiểm tra: {parts.join('; ')}
        </span>
        {second && <SecondOpinionNote opinion={second} />}
      </>
    )
  }
  if (checked > 0 || evidenceCount > 0) {
    return (
      <>
        <span className="verify verify-ok">
          <Icon name="shield" size={14} />
          {checked > 0
            ? ` Đã đối chiếu ${checked} số liệu với dữ liệu truy vấn`
            : ` Dựa trên ${evidenceCount} chứng cứ`}
        </span>
        {second && <SecondOpinionNote opinion={second} />}
      </>
    )
  }
  return second ? <SecondOpinionNote opinion={second} /> : null
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
