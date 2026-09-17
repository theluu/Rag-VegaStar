import { useCallback, useEffect, useRef, useState } from 'react'
import { ChatPanel } from './components/ChatPanel'
import { ConversationList } from './components/ConversationList'
import { LayerPanel } from './components/LayerPanel'
import { Icon } from './components/Icon'
import { MapView, type MapLayer } from './components/MapView'
import { api, streamChat, type Conversation, type MapDataRef } from './lib/api'
import { layerMeta } from './lib/layers'
import { buildTurns, type Turn } from './lib/transcript'

// Khi mở lại hội thoại cũ, chỉ nạp lại vài lớp bản đồ gần nhất
const RESTORED_LAYERS = 6

type MobileView = 'chat' | 'map'

export default function App() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [turns, setTurns] = useState<Turn[]>([])
  const [layers, setLayers] = useState<MapLayer[]>([])
  const [fitTo, setFitTo] = useState<{ id: string; nonce: number } | null>(null)
  const [streaming, setStreaming] = useState(false)
  const [loading, setLoading] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const [apiOnline, setApiOnline] = useState(true)
  const [railOpen, setRailOpen] = useState(false)
  const [mobileView, setMobileView] = useState<MobileView>('chat')
  const abortRef = useRef<AbortController | null>(null)

  const refreshList = useCallback(async () => {
    try {
      setConversations(await api.listConversations())
      setApiOnline(true)
    } catch (e) {
      setApiOnline(false)
      setProblem(`Không kết nối được API (${(e as Error).message}). Kiểm tra server và VITE_API_BASE_URL.`)
    }
  }, [])

  useEffect(() => {
    void refreshList()
  }, [refreshList])

  // Trên điện thoại, bản đồ đổi kích thước khi chuyển tab → căn lại lớp mới nhất
  const newestLayerId = layers[layers.length - 1]?.id
  useEffect(() => {
    if (mobileView === 'map' && newestLayerId) {
      const t = window.setTimeout(() => setFitTo({ id: newestLayerId, nonce: Date.now() }), 50)
      return () => window.clearTimeout(t)
    }
  }, [mobileView, newestLayerId])

  const addLayer = useCallback(async (ref: Pick<MapDataRef, 'id' | 'kind'>, focus: boolean) => {
    const data = await api.getMapData(ref.id)
    const meta = layerMeta(data.kind, data.summary)
    setLayers((prev) => [
      ...prev.filter((l) => l.id !== data.id),
      { id: data.id, kind: data.kind, geojson: data.geojson, bbox: data.bbox, summary: data.summary, visible: true, ...meta },
    ])
    if (focus) setFitTo({ id: data.id, nonce: Date.now() })
  }, [])

  const openConversation = useCallback(
    async (id: string) => {
      abortRef.current?.abort()
      setActiveId(id)
      setRailOpen(false)
      setLoading(true)
      setTurns([])
      setLayers([])
      try {
        const [messages, refs] = await Promise.all([api.listMessages(id), api.listMapData(id)])
        setTurns(buildTurns(messages))
        const recent = refs.slice(-RESTORED_LAYERS)
        for (const [i, ref] of recent.entries()) {
          await addLayer(ref, i === recent.length - 1)
        }
      } catch (e) {
        setProblem(`Không mở được cuộc hỏi đáp: ${(e as Error).message}`)
      } finally {
        setLoading(false)
      }
    },
    [addLayer],
  )

  // Tạo hội thoại trên server khi gửi câu hỏi đầu tiên (không sinh hội thoại rỗng)
  const createConversation = useCallback(async () => {
    const conv = await api.createConversation()
    setActiveId(conv.id)
    await refreshList()
    return conv.id
  }, [refreshList])

  const startNew = useCallback(() => {
    abortRef.current?.abort()
    setActiveId(null)
    setTurns([])
    setLayers([])
    setRailOpen(false)
    setMobileView('chat')
  }, [])

  const deleteConversation = useCallback(
    async (id: string) => {
      await api.deleteConversation(id)
      if (id === activeId) {
        setActiveId(null)
        setTurns([])
        setLayers([])
      }
      await refreshList()
    },
    [activeId, refreshList],
  )

  const updateLast = (fn: (t: Turn) => Turn) =>
    setTurns((prev) => (prev.length ? [...prev.slice(0, -1), fn(prev[prev.length - 1])] : prev))

  const send = useCallback(
    async (text: string) => {
      const convId = activeId ?? (await createConversation())
      const controller = new AbortController()
      abortRef.current = controller
      setStreaming(true)
      setTurns((prev) => [
        ...prev,
        { key: `live-${Date.now()}`, question: text, steps: [], answer: '', mapIds: [], pending: true },
      ])
      try {
        await streamChat(
          convId,
          text,
          {
            onToken: (t) => updateLast((turn) => ({ ...turn, answer: turn.answer + t })),
            onToolCall: (c) =>
              updateLast((turn) => ({
                ...turn,
                // Văn bản trước lời gọi tool chỉ là phần dẫn; câu trả lời thật đến sau khi có dữ liệu
                answer: '',
                steps: [...turn.steps, { id: c.id, name: c.name, args: c.args }],
              })),
            onToolResult: (r) =>
              updateLast((turn) => ({
                ...turn,
                steps: turn.steps.map((s) => (s.id === r.id ? { ...s, ok: r.ok, summary: r.summary } : s)),
              })),
            onData: (d) => {
              updateLast((turn) => ({ ...turn, mapIds: [...turn.mapIds, d.data_id] }))
              void addLayer({ id: d.data_id, kind: d.kind }, true)
            },
            onMemory: (m) =>
              updateLast((turn) => ({
                ...turn,
                memory: {
                  window: m.window_turns,
                  summary: m.summary_used,
                  recalled: m.retrieved.map((r) => ({ turn: r.turn_no, score: r.score })),
                },
              })),
            onError: (e) => updateLast((turn) => ({ ...turn, error: e.message })),
            onDone: () => updateLast((turn) => ({ ...turn, pending: false })),
          },
          controller.signal,
        )
      } catch (e) {
        if (controller.signal.aborted) {
          updateLast((turn) => ({ ...turn, pending: false, interrupted: true }))
        } else {
          updateLast((turn) => ({ ...turn, pending: false, error: (e as Error).message }))
        }
      } finally {
        updateLast((turn) => ({ ...turn, pending: false }))
        setStreaming(false)
        abortRef.current = null
        void refreshList()
      }
    },
    [activeId, addLayer, createConversation, refreshList],
  )

  const active = conversations.find((c) => c.id === activeId)

  // Chip "xem trên bản đồ" trong câu trả lời: hiện lại lớp (nạp nếu chưa có) và phóng tới đó
  const showLayer = useCallback(
    (id: string) => {
      setMobileView('map')
      if (layers.some((l) => l.id === id)) {
        setLayers((ls) => ls.map((l) => (l.id === id ? { ...l, visible: true } : l)))
        setFitTo({ id, nonce: Date.now() })
      } else {
        void addLayer({ id, kind: 'track' }, true)
      }
    },
    [addLayer, layers],
  )

  return (
    <div className={`app view-${mobileView}${railOpen ? ' rail-open' : ''}`}>
      <ConversationList
        conversations={conversations}
        activeId={activeId}
        apiOnline={apiOnline}
        onSelect={(id) => void openConversation(id)}
        onCreate={startNew}
        onDelete={(id) => void deleteConversation(id)}
      />
      {railOpen && (
        <button type="button" className="scrim" onClick={() => setRailOpen(false)} aria-label="Đóng danh sách hội thoại" />
      )}
      <div className="mobile-bar">
        <button type="button" className="icon-button" onClick={() => setRailOpen((o) => !o)} aria-expanded={railOpen} aria-label="Danh sách hội thoại">
          <Icon name="menu" size={20} />
        </button>
        <div className="segmented" role="tablist">
          <button type="button" role="tab" aria-selected={mobileView === 'chat'} onClick={() => setMobileView('chat')}>
            Hỏi đáp
          </button>
          <button type="button" role="tab" aria-selected={mobileView === 'map'} onClick={() => setMobileView('map')}>
            Bản đồ{layers.length ? ` (${layers.length})` : ''}
          </button>
        </div>
      </div>
      <main className="chart">
        <MapView layers={layers} fitTo={fitTo} />
        <div className="map-badge">Vùng dữ liệu 102–118°E, 6–23°N, 10–12/09/2026 (UTC)</div>
        <LayerPanel
          layers={layers}
          onToggle={(id) => setLayers((ls) => ls.map((l) => (l.id === id ? { ...l, visible: !l.visible } : l)))}
          onRemove={(id) => setLayers((ls) => ls.filter((l) => l.id !== id))}
          onFocus={(id) => setFitTo({ id, nonce: Date.now() })}
          onClear={() => setLayers([])}
        />
      </main>
      <ChatPanel
        title={active?.title ?? 'Cuộc hỏi đáp mới'}
        turns={turns}
        layers={layers}
        streaming={streaming}
        loading={loading}
        onSend={(t) => void send(t)}
        onStop={() => abortRef.current?.abort()}
        onShowLayer={showLayer}
      />
      {problem && (
        <div className="toast" role="alert">
          <Icon name="alert" size={18} />
          <span>{problem}</span>
          <button type="button" className="icon-button" onClick={() => setProblem(null)} aria-label="Đóng thông báo">
            <Icon name="close" size={16} />
          </button>
        </div>
      )}
    </div>
  )
}
