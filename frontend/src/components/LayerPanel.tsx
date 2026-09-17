import { COLORS } from './MapView'
import type { MapLayer } from './MapView'

const SWATCH: Record<MapLayer['kind'], string> = {
  position: COLORS.magenta,
  track: COLORS.magenta,
  gaps: COLORS.amber,
  tracks: 'conic-gradient(#B3246B 0 25%, #1F6F8B 0 50%, #C98600 0 75%, #3A7D44 0)',
}

interface Props {
  layers: MapLayer[]
  onToggle: (id: string) => void
  onRemove: (id: string) => void
  onFocus: (id: string) => void
  onClear: () => void
}

export function LayerPanel({ layers, onToggle, onRemove, onFocus, onClear }: Props) {
  if (layers.length === 0) {
    return (
      <div className="legend legend-empty">
        <p>Hỏi về vị trí, hành trình hoặc lần mất tín hiệu của một tàu để vẽ lên bản đồ.</p>
      </div>
    )
  }
  return (
    <div className="legend" aria-label="Các lớp trên bản đồ">
      <div className="legend-head">
        <h2>Trên bản đồ</h2>
        <button type="button" className="text-button" onClick={onClear}>
          Xoá bản đồ
        </button>
      </div>
      <ul>
        {layers.map((l) => (
          <li key={l.id} className={l.visible ? '' : 'is-hidden'}>
            <label className="legend-toggle">
              <input type="checkbox" checked={l.visible} onChange={() => onToggle(l.id)} />
              <span className={`swatch swatch-${l.kind}`} style={{ background: SWATCH[l.kind] }} aria-hidden />
            </label>
            <button type="button" className="legend-label" onClick={() => onFocus(l.id)} title="Phóng tới lớp này">
              <span>{l.label}</span>
              <small>{l.detail}</small>
            </button>
            <button type="button" className="icon-button" onClick={() => onRemove(l.id)} aria-label={`Bỏ lớp ${l.label}`}>
              ×
            </button>
          </li>
        ))}
      </ul>
      <dl className="legend-key">
        <div><dt><i className="key-dot" style={{ background: COLORS.ink }} /></dt><dd>điểm đầu</dd></div>
        <div><dt><i className="key-ring" /></dt><dd>điểm cuối</dd></div>
        <div><dt><i className="key-dot" style={{ background: COLORS.amber }} /></dt><dd>mất tín hiệu</dd></div>
        <div><dt><i className="key-dot" style={{ background: COLORS.teal }} /></dt><dd>có tín hiệu lại</dd></div>
      </dl>
    </div>
  )
}
