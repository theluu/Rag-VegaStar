import { useState } from 'react'
import { Icon, type IconName } from './Icon'
import { COLORS, TRACK_PALETTE, type MapLayer } from './MapView'

const KIND_ICON: Record<MapLayer['kind'], IconName> = {
  position: 'pin',
  track: 'route',
  gaps: 'signalOff',
  tracks: 'fleet',
}

const KIND_COLOR: Record<MapLayer['kind'], string> = {
  position: COLORS.magenta,
  track: COLORS.magenta,
  gaps: COLORS.amber,
  tracks: COLORS.ink,
}

interface RankedVessel {
  vessel_id: string
  name: string
  distance_nm: number
}

const nm = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 0 })

function Ranking({ layer }: { layer: MapLayer }) {
  const vessels = (layer.summary.vessels as RankedVessel[] | undefined) ?? []
  if (vessels.length === 0) return null
  const top = vessels.slice(0, 5)
  const max = top[0].distance_nm || 1
  return (
    <div className="ranking">
      <h3>Đi xa nhất</h3>
      <ol>
        {top.map((v, i) => (
          <li key={v.vessel_id}>
            <span className="rank-color" style={{ background: TRACK_PALETTE[i % TRACK_PALETTE.length] }} />
            <span className="rank-name">{v.name}</span>
            <span className="rank-bar" aria-hidden>
              <span style={{ width: `${(v.distance_nm / max) * 100}%`, background: TRACK_PALETTE[i % TRACK_PALETTE.length] }} />
            </span>
            <span className="rank-value">{nm.format(v.distance_nm)} hl</span>
          </li>
        ))}
      </ol>
      {vessels.length > top.length && <p className="ranking-more">và {vessels.length - top.length} tàu khác trên bản đồ</p>}
    </div>
  )
}

interface Props {
  layers: MapLayer[]
  onToggle: (id: string) => void
  onRemove: (id: string) => void
  onFocus: (id: string) => void
  onClear: () => void
}

export function LayerPanel({ layers, onToggle, onRemove, onFocus, onClear }: Props) {
  // Màn hình hẹp: thu gọn sẵn để nhường chỗ cho bản đồ
  const [collapsed, setCollapsed] = useState(() => window.matchMedia('(max-width: 880px)').matches)
  const newest = layers[layers.length - 1]
  const kinds = new Set(layers.filter((l) => l.visible).map((l) => l.kind))

  if (layers.length === 0) {
    return (
      <aside className="legend legend-empty">
        <Icon name="layers" size={18} />
        <p>Vị trí, hành trình và các lần mất tín hiệu sẽ hiện ở đây khi bạn hỏi.</p>
      </aside>
    )
  }

  return (
    <aside className={`legend${collapsed ? ' is-collapsed' : ''}`} aria-label="Các lớp trên bản đồ">
      <header className="legend-head">
        <button type="button" className="legend-title" onClick={() => setCollapsed((c) => !c)} aria-expanded={!collapsed}>
          <Icon name="layers" size={16} />
          Trên bản đồ <span className="count">{layers.length}</span>
        </button>
        <button type="button" className="link-button" onClick={onClear}>
          Xoá hết
        </button>
      </header>

      {!collapsed && (
        <>
          <ul className="layer-list">
            {[...layers].reverse().map((l) => (
              <li key={l.id} className={l.visible ? '' : 'is-hidden'}>
                <span className="layer-icon" style={{ color: KIND_COLOR[l.kind] }}>
                  <Icon name={KIND_ICON[l.kind]} size={16} />
                </span>
                <button type="button" className="layer-label" onClick={() => onFocus(l.id)} title="Phóng tới lớp này">
                  <span>{l.label}</span>
                  <small>{l.detail}</small>
                </button>
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => onToggle(l.id)}
                  aria-label={l.visible ? `Ẩn ${l.label}` : `Hiện ${l.label}`}
                  aria-pressed={!l.visible}
                >
                  <Icon name={l.visible ? 'eye' : 'eyeOff'} size={16} />
                </button>
                <button type="button" className="icon-button" onClick={() => onRemove(l.id)} aria-label={`Bỏ ${l.label}`}>
                  <Icon name="close" size={15} />
                </button>
              </li>
            ))}
          </ul>

          {newest?.kind === 'tracks' && <Ranking layer={newest} />}

          <dl className="legend-key">
            {kinds.has('position') && (
              <div><dt><i className="key-dot" style={{ background: COLORS.magenta }} /></dt><dd>vị trí trả lời</dd></div>
            )}
            {kinds.has('track') && (
              <>
                <div><dt><i className="key-line" /></dt><dd>hành trình</dd></div>
                <div><dt><i className="key-dot" style={{ background: COLORS.ink }} /></dt><dd>điểm đầu</dd></div>
                <div><dt><i className="key-ring" /></dt><dd>điểm cuối</dd></div>
              </>
            )}
            {kinds.has('gaps') && (
              <>
                <div><dt><i className="key-dot" style={{ background: COLORS.amber }} /></dt><dd>mất tín hiệu</dd></div>
                <div><dt><i className="key-dot" style={{ background: COLORS.teal }} /></dt><dd>có tín hiệu lại</dd></div>
              </>
            )}
            <div><dt><i className="key-dash" /></dt><dd>vùng dữ liệu</dd></div>
          </dl>
        </>
      )}
    </aside>
  )
}
