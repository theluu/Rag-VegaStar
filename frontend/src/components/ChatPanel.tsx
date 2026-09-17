import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { describeArgs, toolLabel, type Turn } from '../lib/transcript'

const EXAMPLES = [
  'Cho tôi thông tin về tàu KOTA GAYA.',
  'Tàu có MMSI 563240200 đã đi từ đâu đến đâu trong ngày 11/09/2026?',
  'Tàu nào mất tín hiệu AIS lâu nhất trong dữ liệu?',
  'Hiển thị hành trình của tất cả tàu do Evergreen Marine Corp khai thác từ 10/09 đến hết 12/09/2026.',
]

interface Props {
  title: string
  turns: Turn[]
  streaming: boolean
  loading: boolean
  onSend: (text: string) => void
  onStop: () => void
}

function ToolLog({ turn }: { turn: Turn }) {
  if (turn.steps.length === 0 && !turn.memory?.recalled.length) return null
  return (
    <ol className="log" aria-label="Các bước tra cứu">
      {turn.memory && turn.memory.recalled.length > 0 && (
        <li className="log-memory">
          <span className="log-name">Nhớ lại từ bộ nhớ dài hạn</span>
          <span className="log-args">lượt {turn.memory.recalled.join(', ')}</span>
        </li>
      )}
      {turn.steps.map((s) => (
        <li key={s.id} className={s.ok === false ? 'log-failed' : s.ok ? 'log-done' : 'log-running'}>
          <span className="log-name">{toolLabel(s.name)}</span>
          <span className="log-args">{describeArgs(s.args)}</span>
          {s.ok === false && <span className="log-error">{String(s.summary?.error ?? 'lỗi')}</span>}
        </li>
      ))}
    </ol>
  )
}

export function ChatPanel({ title, turns, streaming, loading, onSend, onStop }: Props) {
  const [draft, setDraft] = useState('')
  const scroller = useRef<HTMLDivElement>(null)
  const last = turns[turns.length - 1]

  useEffect(() => {
    const el = scroller.current
    if (el) el.scrollTop = el.scrollHeight
  }, [turns.length, last?.answer, last?.steps.length])

  const submit = (e?: FormEvent) => {
    e?.preventDefault()
    const text = draft.trim()
    if (!text || streaming) return
    onSend(text)
    setDraft('')
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) submit()
  }

  return (
    <section className="chat" aria-label="Hỏi đáp">
      <header className="chat-head">
        <h1>{title}</h1>
      </header>
      <div className="chat-scroll" ref={scroller} aria-live="polite" aria-busy={streaming}>
        {loading && <p className="chat-note">Đang mở cuộc hỏi đáp…</p>}
        {!loading && turns.length === 0 && (
          <div className="starter">
            <p>
              Hỏi về 1.000 tàu trong vùng 102–118°E, 6–23°N từ 10 đến 12/09/2026: tàu của ai, đang ở đâu, đã đi
              những đâu, có tắt tín hiệu AIS không.
            </p>
            <ul>
              {EXAMPLES.map((q) => (
                <li key={q}>
                  <button type="button" onClick={() => onSend(q)} disabled={streaming}>
                    {q}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        {turns.map((t) => (
          <article key={t.key} className="turn">
            <p className="question">{t.question}</p>
            <ToolLog turn={t} />
            {t.answer ? (
              <div className="answer">
                <Markdown remarkPlugins={[remarkGfm]}>{t.answer}</Markdown>
                {t.pending && <span className="caret" aria-hidden />}
              </div>
            ) : (
              t.pending && <p className="chat-note">{t.steps.length ? 'Đang tra dữ liệu…' : 'Đang suy nghĩ…'}</p>
            )}
            {t.interrupted && <p className="chat-note">Câu trả lời đã bị dừng giữa chừng.</p>}
            {t.error && <p className="chat-error" role="alert">{t.error}</p>}
          </article>
        ))}
      </div>
      <form className="composer" onSubmit={submit}>
        <label htmlFor="question" className="visually-hidden">
          Câu hỏi
        </label>
        <textarea
          id="question"
          rows={2}
          value={draft}
          placeholder="Hỏi về một tàu, công ty hoặc khoảng thời gian…"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
        />
        {streaming ? (
          <button type="button" className="secondary-button" onClick={onStop}>
            Dừng
          </button>
        ) : (
          <button type="submit" className="primary-button" disabled={!draft.trim()}>
            Gửi
          </button>
        )}
      </form>
    </section>
  )
}
