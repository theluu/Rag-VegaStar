import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, type RecentTurn, type Stats, type StatsRange, type TurnOutcome } from '../lib/api'
import {
  OUTCOMES,
  RANGES,
  evalCategoryLabel,
  fillDays,
  fmtCompact,
  fmtDateTime,
  fmtDay,
  fmtInt,
  fmtMs,
  fmtPercent,
  fmtSeconds,
  fmtUptime,
  fmtUsd,
  guardActionLabel,
  guardKindLabel,
  niceMax,
  shipGroupLabel,
  todayIn,
  type DayPoint,
} from '../lib/stats'
import { toolMeta } from '../lib/transcript'
import { Icon, Spinner, type IconName } from './Icon'

const REFRESH_MS = 30_000
const RANGE_KEY = 'vc.stats.range'

function readRange(): StatsRange {
  try {
    const v = localStorage.getItem(RANGE_KEY)
    if (v && RANGES.some((r) => r.value === v)) return v as StatsRange
  } catch {
    // trình duyệt chặn storage → dùng mặc định
  }
  return '7d'
}

function saveRange(v: StatsRange) {
  try {
    localStorage.setItem(RANGE_KEY, v)
  } catch {
    // bỏ qua
  }
}

interface Props {
  onOpenConversation: (id: string) => void
}

export function StatsView({ onOpenConversation }: Props) {
  const [range, setRange] = useState<StatsRange>(readRange)
  const [stats, setStats] = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const load = useCallback(async (r: StatsRange) => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setLoading(true)
    try {
      const data = await api.getStats(r, controller.signal)
      setStats(data)
      setError(null)
    } catch (e) {
      if (!controller.signal.aborted) setError((e as Error).message)
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load(range)
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void load(range)
    }, REFRESH_MS)
    return () => {
      window.clearInterval(timer)
      abortRef.current?.abort()
    }
  }, [load, range])

  const changeRange = (r: StatsRange) => {
    saveRange(r)
    setRange(r)
  }

  return (
    <section className="stats" aria-labelledby="stats-title">
      <header className="stats-head">
        <div>
          <h1 id="stats-title">Thống kê vận hành</h1>
          <p>
            {stats
              ? `Cập nhật ${fmtDateTime(stats.generated_at)}, tự làm mới mỗi 30 giây. Ngày tính theo giờ ${stats.timezone}.`
              : 'Số lượt hỏi đáp, chi phí, độ trễ, công cụ, guardrail và chất lượng câu trả lời.'}
          </p>
        </div>
        <div className="stats-controls">
          <div className="range-picker" role="radiogroup" aria-label="Khoảng thời gian">
            {RANGES.map((r) => (
              <button
                key={r.value}
                type="button"
                role="radio"
                aria-checked={range === r.value}
                onClick={() => changeRange(r.value)}
              >
                {r.label}
              </button>
            ))}
          </div>
          <button type="button" className="refresh-button" onClick={() => void load(range)} disabled={loading}>
            {loading ? <Spinner size={15} /> : <Icon name="refresh" size={15} />}
            Làm mới
          </button>
        </div>
      </header>

      {error && (
        <div className="stats-error" role="alert">
          <Icon name="alert" size={18} />
          <div>
            <strong>Không tải được số liệu.</strong> {error}
            <br />
            Kiểm tra API đang chạy và biến <code>STATS_ENABLED</code>, rồi bấm Làm mới.
          </div>
        </div>
      )}

      {!stats && loading && !error && <StatsSkeleton />}
      {stats && <Dashboard stats={stats} onOpenConversation={onOpenConversation} />}
    </section>
  )
}

function StatsSkeleton() {
  return (
    <div className="stats-grid" aria-busy="true" aria-label="Đang tải số liệu">
      {Array.from({ length: 5 }, (_, i) => (
        <div key={i} className="kpi skeleton" />
      ))}
      <div className="panel skeleton span-8" style={{ height: 260 }} />
      <div className="panel skeleton span-4" style={{ height: 260 }} />
    </div>
  )
}

function Dashboard({ stats, onOpenConversation }: { stats: Stats } & Props) {
  const { overview: ov, latency, quality } = stats
  const days = useMemo(
    () => fillDays(stats.daily, stats.range, todayIn(stats.timezone, new Date(stats.generated_at))),
    [stats],
  )
  const empty = ov.turns === 0

  return (
    <div className="stats-grid">
      <Kpi
        icon="chat"
        label="Lượt hỏi đáp"
        value={fmtInt(ov.turns)}
        note={`${fmtInt(ov.conversations)} cuộc hỏi đáp, ${(ov.tool_calls_per_turn ?? 0).toLocaleString('vi-VN')} lần gọi công cụ mỗi lượt`}
      />
      <Kpi
        icon="check"
        label="Trả lời thành công"
        value={fmtPercent(ov.success_rate, 1)}
        note={`${fmtInt(ov.outcomes.blocked)} lượt bị chặn, ${fmtInt(ov.outcomes.error)} lỗi`}
        tone={ov.outcomes.error > 0 ? 'warn' : undefined}
      />
      <Kpi
        icon="coins"
        label="Chi phí LLM"
        value={fmtUsd(ov.cost_usd)}
        note={`${fmtUsd(ov.cost_per_turn_usd)} mỗi lượt, ${fmtCompact(ov.prompt_tokens + ov.completion_tokens)} token`}
      />
      <Kpi
        icon="clock"
        label="Thời gian tới chữ đầu tiên"
        value={fmtSeconds(latency.ttft_p50)}
        note={
          latency.measured_turns
            ? `Trung vị. p95 ${fmtSeconds(latency.ttft_p95)}; cả lượt ${fmtSeconds(latency.duration_p50)}`
            : 'Chưa có lượt nào được đo trong khoảng này'
        }
      />
      <Kpi
        icon="shield"
        label="Câu trả lời khớp dữ liệu"
        value={fmtPercent(quality.grounded_rate, 1)}
        note={`${fmtInt(quality.numbers_checked)} con số đã đối chiếu trong ${fmtInt(quality.verified_answers)} câu trả lời`}
        tone={quality.grounded_rate != null && quality.grounded_rate < 1 ? 'warn' : undefined}
      />

      <Panel
        className="span-8"
        title="Lượt hỏi đáp theo ngày"
        subtitle={empty ? 'Chưa có lượt hỏi đáp nào trong khoảng này.' : 'Di chuột lên cột để xem chi tiết.'}
      >
        <DailyChart days={days} metric="turns" />
      </Panel>

      <Panel className="span-4" title="Kết quả các lượt" subtitle={`${fmtInt(ov.turns)} lượt trong khoảng đã chọn`}>
        <OutcomeBreakdown outcomes={ov.outcomes} total={ov.turns} />
        <dl className="mini-facts">
          <div>
            <dt>Lượt đầu tiên</dt>
            <dd>{fmtDateTime(ov.first_turn_at)}</dd>
          </div>
          <div>
            <dt>Lượt gần nhất</dt>
            <dd>{fmtDateTime(ov.last_turn_at)}</dd>
          </div>
        </dl>
      </Panel>

      <Panel className="span-8" title="Công cụ truy vấn" subtitle="Số lần mô hình gọi từng công cụ, tỉ lệ thành công, cache và độ trễ.">
        <ToolTable stats={stats} />
      </Panel>

      <Panel className="span-4" title="Chi phí theo ngày" subtitle={`Giá ${fmtUsd(stats.runtime.price_input_per_m)} / ${fmtUsd(stats.runtime.price_output_per_m)} mỗi triệu token vào / ra`}>
        <DailyChart days={days} metric="cost_usd" compact />
        <dl className="mini-facts">
          <div>
            <dt>Token vào / ra</dt>
            <dd>
              {fmtInt(ov.prompt_tokens)} / {fmtInt(ov.completion_tokens)}
            </dd>
          </div>
          <div>
            <dt>Chi phí trung bình mỗi lượt</dt>
            <dd>{fmtUsd(ov.cost_per_turn_usd)}</dd>
          </div>
          <div>
            <dt>Ước tính cho 10.000 lượt</dt>
            <dd>{ov.cost_per_turn_usd == null ? '—' : fmtUsd(ov.cost_per_turn_usd * 10_000)}</dd>
          </div>
        </dl>
      </Panel>

      <Panel className="span-4" title="Chứng cứ và kiểm chứng" subtitle="Mỗi câu trả lời dùng dữ liệu phải trích mã chứng cứ và khớp số liệu.">
        <Meter
          label="Câu trả lời có trích chứng cứ"
          ratio={quality.citation_rate}
          detail={`${fmtInt(quality.cited_answers)} / ${fmtInt(quality.answers_with_evidence)} câu trả lời dùng dữ liệu`}
        />
        <Meter
          label="Số liệu khớp dữ liệu truy vấn"
          ratio={quality.grounded_rate}
          detail={`${fmtInt(quality.grounded_answers)} / ${fmtInt(quality.verified_answers)} câu trả lời đã kiểm tra`}
        />
        <p className="panel-note">
          Hệ thống tự bổ sung mã chứng cứ cho {fmtInt(quality.auto_cited)} câu trả lời mà mô hình quên trích.
        </p>
      </Panel>

      <Panel className="span-4" title="Guardrails" subtitle="Các lần chặn, cảnh báo hoặc che nội dung.">
        <GuardrailList items={stats.guardrails} />
      </Panel>

      <Panel className="span-4" title="RAG và bộ nhớ" subtitle="Kho tri thức hàng hải và bộ nhớ dài hạn trong pgvector.">
        <div className="fact-grid">
          <Fact label="Lượt tra kho tri thức" value={fmtInt(stats.rag.knowledge_searches)} />
          <Fact label="Tài liệu / đoạn tri thức" value={`${stats.rag.knowledge_docs} / ${stats.rag.knowledge_chunks}`} />
          <Fact label="Ký ức hội thoại (vector)" value={fmtInt(stats.rag.memory_chunks)} />
          <Fact label="Hội thoại đã tóm tắt" value={fmtInt(stats.rag.summarized_conversations)} />
          <Fact label="Cache công cụ trúng" value={fmtPercent(stats.cache.hit_rate)} hint={`${fmtInt(stats.cache.hits)} / ${fmtInt(stats.cache.lookups)} lần tra`} />
          <Fact label="Mục đang cache" value={`${fmtInt(stats.cache.entries)} / ${fmtInt(stats.cache.max_entries)}`} />
        </div>
      </Panel>

      <Panel
        className="span-12"
        title="Lượt gần đây"
        subtitle="Bấm vào một dòng để mở cuộc hỏi đáp đó."
      >
        <RecentTable turns={stats.recent_turns} onOpen={onOpenConversation} />
      </Panel>

      <Panel className="span-5" title="Harness đánh giá" subtitle="Bộ câu hỏi chấm tự động với mô hình thật (evals/run.py).">
        <EvalPanel stats={stats} />
      </Panel>

      <Panel className="span-4" title="Dữ liệu nguồn" subtitle={dataRange(stats)}>
        <DataPanel stats={stats} />
      </Panel>

      <Panel className="span-3" title="Cấu hình đang chạy" subtitle={`Đã chạy ${fmtUptime(stats.runtime.started_at)}`}>
        <RuntimePanel stats={stats} />
      </Panel>
    </div>
  )
}

function dataRange(stats: Stats) {
  const { positions_from: from, positions_to: to } = stats.data
  if (!from || !to) return 'Chưa nạp dữ liệu AIS.'
  const f = new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC' })
  return `AIS từ ${f.format(new Date(from))} đến ${f.format(new Date(to))} (UTC)`
}

// ---------------------------------------------------------------- khối dựng

function Panel({ title, subtitle, className, children }: { title: string; subtitle?: string; className?: string; children: ReactNode }) {
  return (
    <section className={`panel ${className ?? ''}`}>
      <header className="panel-head">
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </header>
      {children}
    </section>
  )
}

function Kpi({ icon, label, value, note, tone }: { icon: IconName; label: string; value: string; note: string; tone?: 'warn' }) {
  return (
    <div className={`kpi${tone ? ` kpi-${tone}` : ''}`}>
      <div className="kpi-label">
        <Icon name={icon} size={16} />
        {label}
      </div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-note">{note}</div>
    </div>
  )
}

function Fact({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="fact">
      <span className="fact-value">{value}</span>
      <span className="fact-label">{label}</span>
      {hint && <span className="fact-hint">{hint}</span>}
    </div>
  )
}

function Meter({ label, ratio, detail }: { label: string; ratio: number | null; detail: string }) {
  return (
    <div className="meter">
      <div className="meter-top">
        <span>{label}</span>
        <strong>{fmtPercent(ratio, 1)}</strong>
      </div>
      <div className="meter-track" role="img" aria-label={`${label}: ${fmtPercent(ratio, 1)}`}>
        <div className="meter-fill" style={{ width: `${(ratio ?? 0) * 100}%` }} />
      </div>
      <div className="meter-detail">{detail}</div>
    </div>
  )
}

// ---------------------------------------------------------------- biểu đồ theo ngày

/** Độ rộng thật của phần tử để vẽ SVG đúng pixel (chữ trục không bị co giãn). */
function useWidth<T extends HTMLElement>(fallback: number) {
  const ref = useRef<T | null>(null)
  const [width, setWidth] = useState(fallback)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(240, Math.round(entry.contentRect.width))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, width] as const
}

function DailyChart({ days, metric, compact }: { days: DayPoint[]; metric: 'turns' | 'cost_usd'; compact?: boolean }) {
  const [hover, setHover] = useState<number | null>(null)
  const [boxRef, W] = useWidth<HTMLDivElement>(640)
  const H = compact ? 180 : 230
  const pad = { top: 12, right: 8, bottom: 26, left: metric === 'cost_usd' ? 52 : 36 }
  const values = days.map((d) => d[metric])
  const max = niceMax(Math.max(...values, 0))
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * max)
  const innerW = W - pad.left - pad.right
  const innerH = H - pad.top - pad.bottom
  const slot = innerW / Math.max(days.length, 1)
  const barW = Math.max(3, Math.min(34, slot - 4))
  const labelEvery = Math.ceil(days.length / Math.max(2, Math.floor(innerW / 64)))
  const fmt = metric === 'turns' ? (v: number) => fmtInt(Math.round(v)) : fmtUsd
  const y = (v: number) => pad.top + innerH - (v / max) * innerH
  const active = hover == null ? null : days[hover]
  const title = metric === 'turns' ? 'Lượt hỏi đáp theo ngày' : 'Chi phí theo ngày'

  return (
    <div className="chart-box" ref={boxRef} onMouseLeave={() => setHover(null)}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="bar-chart" role="img" aria-label={title}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.left} x2={W - pad.right} y1={y(t)} y2={y(t)} className={t === 0 ? 'axis-base' : 'grid-line'} />
            <text x={pad.left - 8} y={y(t)} className="axis-label" textAnchor="end" dominantBaseline="middle">
              {fmt(t)}
            </text>
          </g>
        ))}
        {days.map((d, i) => {
          const v = d[metric]
          const x = pad.left + i * slot + (slot - barW) / 2
          const h = Math.max(0, pad.top + innerH - y(v))
          return (
            <g key={d.day}>
              {/* vùng bắt chuột rộng hơn cột */}
              <rect
                x={pad.left + i * slot}
                y={pad.top}
                width={slot}
                height={innerH}
                className="hit-area"
                onMouseEnter={() => setHover(i)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                tabIndex={0}
                aria-label={`${fmtDay(d.day)}: ${fmt(v)}`}
              />
              {v > 0 && (
                <path
                  d={roundedTop(x, pad.top + innerH - h, barW, h, Math.min(4, barW / 2, h))}
                  className={`bar${hover === i ? ' is-hover' : ''}`}
                  pointerEvents="none"
                />
              )}
              {(i % labelEvery === 0 || i === days.length - 1) && (
                <text x={pad.left + i * slot + slot / 2} y={H - 8} className="axis-label" textAnchor="middle">
                  {fmtDay(d.day)}
                </text>
              )}
            </g>
          )
        })}
      </svg>
      {active && hover != null && (
        <div
          className="chart-tip"
          style={{ left: Math.min(Math.max(pad.left + hover * slot + slot / 2, 70), W - 70) }}
          role="status"
        >
          <strong>{fmtDay(active.day)}</strong>
          <span>
            <b>{fmtInt(active.turns)}</b> lượt
          </span>
          {active.blocked > 0 && <span>{fmtInt(active.blocked)} bị chặn</span>}
          {active.errors > 0 && <span>{fmtInt(active.errors)} lỗi</span>}
          <span>{fmtUsd(active.cost_usd)}</span>
        </div>
      )}
      <table className="visually-hidden">
        <caption>{title}</caption>
        <thead>
          <tr>
            <th>Ngày</th>
            <th>Lượt</th>
            <th>Bị chặn</th>
            <th>Chi phí</th>
          </tr>
        </thead>
        <tbody>
          {days.map((d) => (
            <tr key={d.day}>
              <td>{fmtDay(d.day)}</td>
              <td>{d.turns}</td>
              <td>{d.blocked}</td>
              <td>{fmtUsd(d.cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function roundedTop(x: number, y: number, w: number, h: number, r: number) {
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`
}

// ---------------------------------------------------------------- kết quả lượt

function OutcomeBreakdown({ outcomes, total }: { outcomes: Record<TurnOutcome, number>; total: number }) {
  const parts = OUTCOMES.map((o) => ({ ...o, count: outcomes[o.key] ?? 0 }))
  return (
    <div className="outcomes">
      <div className="stack-bar" role="img" aria-label={parts.map((p) => `${p.label} ${p.count}`).join(', ')}>
        {total === 0 && <span className="stack-empty" />}
        {parts
          .filter((p) => p.count > 0)
          .map((p) => (
            <span key={p.key} className={`stack-seg outcome-${p.key}`} style={{ flexGrow: p.count }} />
          ))}
      </div>
      <ul className="legend-list">
        {parts.map((p) => (
          <li key={p.key}>
            <span className={`swatch outcome-${p.key}`} aria-hidden />
            <span className="legend-name">{p.label}</span>
            <span className="legend-count">{fmtInt(p.count)}</span>
            <span className="legend-share">{total ? fmtPercent(p.count / total) : '—'}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ---------------------------------------------------------------- công cụ

function ToolTable({ stats }: { stats: Stats }) {
  const rows = stats.tools
  if (rows.length === 0) return <p className="empty-note">Chưa có lần gọi công cụ nào trong khoảng này.</p>
  const max = Math.max(...rows.map((r) => r.calls))
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>Công cụ</th>
            <th className="col-bar">Số lần gọi</th>
            <th className="num">Thành công</th>
            <th className="num">Trúng cache</th>
            <th className="num">Trung vị</th>
            <th className="num">p95</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const meta = toolMeta(r.name)
            return (
              <tr key={r.name}>
                <td>
                  <span className="tool-name">
                    <span className="tool-icon">
                      <Icon name={meta.icon} size={14} />
                    </span>
                    <span>
                      {meta.label}
                      <code>{r.name}</code>
                    </span>
                  </span>
                </td>
                <td className="col-bar">
                  <span className="bar-cell">
                    <span className="inline-bar">
                      <span style={{ width: `${(r.calls / max) * 100}%` }} />
                    </span>
                    <span className="inline-value">{fmtInt(r.calls)}</span>
                  </span>
                </td>
                <td className={`num${r.success_rate != null && r.success_rate < 1 ? ' is-warn' : ''}`}>
                  {fmtPercent(r.success_rate)}
                </td>
                <td className="num">{fmtPercent(r.cache_hit_rate)}</td>
                <td className="num">{fmtMs(r.ms_p50)}</td>
                <td className="num">{fmtMs(r.ms_p95)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="panel-note">
        Tổng {fmtInt(stats.overview.tool_calls)} lần gọi. Cache và độ trễ chỉ tính các lượt có số đo (
        {fmtInt(stats.latency.measured_turns)} lượt); lượt cũ hơn chỉ có số lần gọi.
      </p>
    </div>
  )
}

// ---------------------------------------------------------------- guardrails

function GuardrailList({ items }: { items: Stats['guardrails'] }) {
  if (items.length === 0) {
    return (
      <p className="empty-note">
        <Icon name="shield" size={16} /> Không có sự kiện guardrail nào trong khoảng này.
      </p>
    )
  }
  return (
    <ul className="guard-list">
      {items.map((g) => (
        <li key={`${g.stage}-${g.action}-${g.kind}`}>
          <span className={`action-badge action-${g.action}`}>{guardActionLabel(g.action)}</span>
          <span className="guard-kind">
            {guardKindLabel(g.kind)}
            <small>{g.stage === 'input' ? 'Đầu vào' : 'Đầu ra'}</small>
          </span>
          <strong>{fmtInt(g.count)}</strong>
        </li>
      ))}
    </ul>
  )
}

// ---------------------------------------------------------------- lượt gần đây

const OUTCOME_TEXT: Record<TurnOutcome, string> = {
  ok: 'Xong',
  blocked: 'Bị chặn',
  error: 'Lỗi',
  cancelled: 'Đã dừng',
}

function RecentTable({ turns, onOpen }: { turns: RecentTurn[]; onOpen: (id: string) => void }) {
  if (turns.length === 0) return <p className="empty-note">Chưa có lượt hỏi đáp nào trong khoảng này.</p>
  return (
    <div className="table-scroll">
      <table className="data-table recent-table">
        <thead>
          <tr>
            <th>Thời điểm</th>
            <th>Câu hỏi</th>
            <th>Công cụ</th>
            <th>Kết quả</th>
            <th className="num">Chứng cứ</th>
            <th className="num">Thời gian</th>
            <th className="num">Token</th>
            <th className="num">Chi phí</th>
          </tr>
        </thead>
        <tbody>
          {turns.map((t) => (
            <tr key={t.id} className="clickable" onClick={() => onOpen(t.conversation_id)}>
              <td className="nowrap">{fmtDateTime(t.created_at)}</td>
              <td className="question-cell">
                <button
                  type="button"
                  className="row-link"
                  onClick={(e) => {
                    e.stopPropagation()
                    onOpen(t.conversation_id)
                  }}
                >
                  {t.question || '(không có nội dung)'}
                </button>
                <span className="conv-ref">
                  {t.title}, lượt {t.turn_no}
                </span>
              </td>
              <td>
                {t.tools.length ? (
                  <span className="tool-chips">
                    {t.tools.map((name) => (
                      <span key={name} className="tool-chip" title={name}>
                        <Icon name={toolMeta(name).icon} size={12} />
                        {toolMeta(name).label}
                      </span>
                    ))}
                  </span>
                ) : (
                  <span className="muted">Không dùng</span>
                )}
              </td>
              <td>
                <span className={`outcome-badge outcome-${t.outcome}`}>{OUTCOME_TEXT[t.outcome]}</span>
                {t.guardrail_kind && <span className="conv-ref">{guardKindLabel(t.guardrail_kind)}</span>}
              </td>
              <td className="num">
                {t.evidence_count > 0 ? (
                  <span className={t.grounded === false ? 'is-warn' : 'is-ok'}>
                    {t.evidence_count} {t.grounded === false ? '(cần xem)' : '✓'}
                  </span>
                ) : (
                  <span className="muted">—</span>
                )}
              </td>
              <td className="num nowrap">{fmtSeconds(t.duration_s)}</td>
              <td className="num">{fmtInt((t.prompt_tokens ?? 0) + (t.completion_tokens ?? 0))}</td>
              <td className="num">{fmtUsd(t.cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------- đánh giá

function EvalPanel({ stats }: { stats: Stats }) {
  const ev = stats.evaluation
  if (!ev) {
    return (
      <p className="empty-note">
        Chưa có báo cáo. Chạy <code>python evals/run.py</code> để tạo <code>results/eval_report.json</code>.
      </p>
    )
  }
  const failed = Object.entries(ev.failed_checks)
  return (
    <div className="eval">
      <div className="eval-hero">
        <div className={`eval-score${ev.passed < ev.cases ? ' is-warn' : ''}`}>
          <span>{fmtPercent(ev.pass_rate)}</span>
          <small>
            {ev.passed}/{ev.cases} ca đạt
          </small>
        </div>
        <dl className="mini-facts">
          <div>
            <dt>Chạy lúc</dt>
            <dd>{fmtDateTime(ev.generated_at)}</dd>
          </div>
          <div>
            <dt>Chi phí cả bộ</dt>
            <dd>{fmtUsd(ev.cost_usd)}</dd>
          </div>
          <div>
            <dt>Chữ đầu / cả lượt</dt>
            <dd>
              {fmtSeconds(ev.first_token_p50)} / {fmtSeconds(ev.total_p50)}
            </dd>
          </div>
        </dl>
      </div>
      <ul className="category-list">
        {ev.categories.map((c) => (
          <li key={c.name}>
            <span className="cat-name">{evalCategoryLabel(c.name)}</span>
            <span className="cat-dots" aria-hidden>
              {Array.from({ length: c.cases }, (_, i) => (
                <span key={i} className={i < c.passed ? 'dot-pass' : 'dot-fail'} />
              ))}
            </span>
            <span className="cat-count">
              {c.passed}/{c.cases}
            </span>
          </li>
        ))}
      </ul>
      {failed.length > 0 && (
        <p className="panel-note is-warn">
          Tiêu chí chưa đạt: {failed.map(([k, v]) => `${k} (${v})`).join(', ')}
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- dữ liệu & cấu hình

function DataPanel({ stats }: { stats: Stats }) {
  const d = stats.data
  const groups = d.ship_type_groups
  const max = Math.max(...groups.map((g) => g.count), 1)
  return (
    <>
      <div className="fact-grid">
        <Fact label="Tàu" value={fmtInt(d.vessels)} />
        <Fact label="Điểm AIS" value={fmtInt(d.positions)} />
        <Fact label="Lần mất tín hiệu" value={fmtInt(d.dark_gaps)} />
        <Fact label="Công ty" value={fmtInt(d.companies)} hint={`${fmtInt(d.ownership_rows)} quan hệ sở hữu`} />
      </div>
      <h3 className="sub-head">Tàu theo loại</h3>
      <ul className="hbar-list">
        {groups.map((g) => (
          <li key={g.name}>
            <span className="hbar-name">{shipGroupLabel(g.name)}</span>
            <span className="hbar-track">
              <span style={{ width: `${(g.count / max) * 100}%` }} />
            </span>
            <span className="hbar-value">{fmtInt(g.count)}</span>
          </li>
        ))}
      </ul>
    </>
  )
}

function RuntimePanel({ stats }: { stats: Stats }) {
  const r = stats.runtime
  const onOff = (v: boolean) => (v ? 'Bật' : 'Tắt')
  const rows: [string, ReactNode][] = [
    ['Mô hình', <code key="m">{r.model}</code>],
    ['Embedding', <code key="e">{r.embedding_model}</code>],
    ['Cửa sổ bộ nhớ', `${r.memory_window_turns} lượt`],
    ['Vòng gọi công cụ tối đa', r.max_tool_iterations],
    ['Kiểm duyệt nội dung', onOff(r.moderation_enabled)],
    ['Đối chiếu số liệu', onOff(r.grounding_enabled)],
    ['Yêu cầu API key', r.auth_required ? 'Có' : 'Không (demo)'],
    ['Giới hạn hỏi', `${r.rate_limit_chat_per_minute} câu/phút`],
    ['Hội thoại đang lưu', fmtInt(stats.data.conversations_total)],
    ['Lớp bản đồ đã tạo', fmtInt(stats.data.map_layers)],
  ]
  return (
    <dl className="runtime-list">
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  )
}
