import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { argChips, toolMeta, type ToolStep, type Turn } from '../lib/transcript'
import { Icon, Spinner } from './Icon'
import type { MapLayer } from './MapView'

function StepRow({ step }: { step: ToolStep }) {
  const meta = toolMeta(step.name)
  const state = step.ok === undefined ? 'running' : step.ok ? 'done' : 'failed'
  return (
    <li className={`step step-${state}`}>
      <span className="step-icon">
        <Icon name={meta.icon} size={15} />
      </span>
      <div className="step-body">
        <div className="step-title">
          <span>{meta.label}</span>
          <span className="step-state" aria-label={state === 'running' ? 'đang chạy' : state === 'done' ? 'xong' : 'lỗi'}>
            {state === 'running' ? <Spinner size={13} /> : <Icon name={state === 'done' ? 'check' : 'close'} size={13} />}
          </span>
        </div>
        <div className="chips">
          {argChips(step.args).map((c) => (
            <span key={c.label + c.value} className="chip">
              <span className="chip-label">{c.label}</span> {c.value}
            </span>
          ))}
        </div>
        {state === 'failed' && <p className="step-error">{String(step.summary?.error ?? 'Tool báo lỗi')}</p>}
      </div>
    </li>
  )
}

interface Props {
  turn: Turn
  layers: MapLayer[]
  onShowLayer: (id: string) => void
}

export function TurnView({ turn, layers, onShowLayer }: Props) {
  const recalled = turn.memory?.recalled ?? []
  const mapped = turn.mapIds.map((id) => ({ id, layer: layers.find((l) => l.id === id) }))
  return (
    <article className="turn">
      <div className="question-row">
        <p className="question">{turn.question}</p>
      </div>

      <div className="reply">
        <div className="reply-head">
          <span className="assistant-mark" aria-hidden>
            <Icon name="compass" size={16} />
          </span>
          <span className="assistant-name">Trợ lý hải đồ</span>
          {turn.pending && (
            <span className="reply-status">
              <Spinner size={12} /> {turn.answer ? 'đang viết' : turn.steps.length ? 'đang tra dữ liệu' : 'đang đọc câu hỏi'}
            </span>
          )}
        </div>

        {recalled.length > 0 && (
          <p className="memory-note">
            <Icon name="memory" size={14} />
            Nhớ lại từ bộ nhớ dài hạn: {recalled.map((r) => `lượt ${r.turn}`).join(', ')}
          </p>
        )}

        {turn.steps.length > 0 && (
          <ol className="steps" aria-label="Các bước tra cứu dữ liệu">
            {turn.steps.map((s) => (
              <StepRow key={s.id} step={s} />
            ))}
          </ol>
        )}

        {turn.answer && (
          <div className="answer">
            <Markdown remarkPlugins={[remarkGfm]}>{turn.answer}</Markdown>
            {turn.pending && <span className="caret" aria-hidden />}
          </div>
        )}

        {mapped.length > 0 && (
          <div className="map-links">
            {mapped.map(({ id, layer }) => (
              <button key={id} type="button" className={`map-link map-link-${layer?.kind ?? 'track'}`} onClick={() => onShowLayer(id)}>
                <Icon name="focus" size={14} />
                {layer ? layer.label : 'Xem trên bản đồ'}
              </button>
            ))}
          </div>
        )}

        {turn.interrupted && <p className="note">Câu trả lời đã bị dừng giữa chừng.</p>}
        {turn.error && (
          <p className="error-note" role="alert">
            <Icon name="alert" size={15} /> {turn.error}
          </p>
        )}
      </div>
    </article>
  )
}
