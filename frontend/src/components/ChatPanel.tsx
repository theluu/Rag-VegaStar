import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import type { Turn } from '../lib/transcript'
import { Icon } from './Icon'
import type { MapLayer } from './MapView'
import { TurnView } from './TurnView'
import { Welcome } from './Welcome'

interface Props {
  title: string
  turns: Turn[]
  layers: MapLayer[]
  streaming: boolean
  loading: boolean
  onSend: (text: string) => void
  onStop: () => void
  onShowLayer: (id: string) => void
}

export function ChatPanel({ title, turns, layers, streaming, loading, onSend, onStop, onShowLayer }: Props) {
  const [draft, setDraft] = useState('')
  const scroller = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLTextAreaElement>(null)
  const last = turns[turns.length - 1]

  useEffect(() => {
    const el = scroller.current
    if (!el) return
    // Chưa có lượt nào (màn hình chào) thì giữ ở đầu, có nội dung mới thì cuộn xuống cuối
    el.scrollTop = turns.length ? el.scrollHeight : 0
  }, [turns.length, last?.answer, last?.steps.length, last?.mapIds.length])

  // Ô nhập tự giãn theo nội dung (tối đa ~6 dòng)
  useEffect(() => {
    const el = input.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 150)}px`
  }, [draft])

  const submit = (e?: FormEvent) => {
    e?.preventDefault()
    const text = draft.trim()
    if (!text || streaming) return
    onSend(text)
    setDraft('')
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <section className="chat" aria-label="Hỏi đáp">
      <header className="chat-head">
        <h1 title={title}>{title}</h1>
        {turns.length > 0 && <span className="turn-count">{turns.length} lượt hỏi</span>}
      </header>

      <div className="chat-scroll" ref={scroller} aria-live="polite" aria-busy={streaming}>
        {loading && <p className="note centered">Đang mở cuộc hỏi đáp…</p>}
        {!loading && turns.length === 0 && <Welcome onPick={onSend} disabled={streaming} />}
        {turns.map((t) => (
          <TurnView key={t.key} turn={t} layers={layers} onShowLayer={onShowLayer} />
        ))}
      </div>

      <form className="composer" onSubmit={submit}>
        <div className="composer-box">
          <label htmlFor="question" className="visually-hidden">
            Câu hỏi
          </label>
          <textarea
            id="question"
            ref={input}
            rows={1}
            value={draft}
            placeholder="Hỏi về tàu, công ty, vị trí, hành trình…"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
          />
          {streaming ? (
            <button type="button" className="round-button stop" onClick={onStop} aria-label="Dừng trả lời">
              <Icon name="stop" size={16} />
            </button>
          ) : (
            <button type="submit" className="round-button" disabled={!draft.trim()} aria-label="Gửi câu hỏi">
              <Icon name="send" size={18} />
            </button>
          )}
        </div>
        <p className="composer-hint">Enter để gửi, Shift + Enter để xuống dòng. Thời gian tính theo UTC.</p>
      </form>
    </section>
  )
}
