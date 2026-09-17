import type { FeatureCollection } from 'geojson'
import {
  Map as MapLibreMap,
  NavigationControl,
  Popup,
  ScaleControl,
  setWorkerUrl,
  type ExpressionSpecification,
  type LayerSpecification,
  type MapGeoJSONFeature,
  type MapLayerMouseEvent,
} from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
// Vite gom thư viện vào bundle nên MapLibre không tự tìm được file worker → bundle worker riêng và chỉ đường
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { useEffect, useRef, useState } from 'react'
import type { MapKind } from '../lib/api'

setWorkerUrl(workerUrl)

export interface MapLayer {
  id: string
  kind: MapKind
  label: string
  detail: string
  geojson: FeatureCollection
  bbox: [number, number, number, number] | null
  visible: boolean
}

const STYLE_URL =
  (import.meta.env.VITE_MAP_STYLE_URL as string | undefined) || 'https://demotiles.maplibre.org/style.json'

// Vùng dữ liệu mặc định lấy từ đề (102–118°E, 6–23°N); bản đồ sẽ tự zoom theo dữ liệu trả về
const INITIAL_BOUNDS: [number, number, number, number] = [102, 6, 118, 23]

export const COLORS = {
  ink: '#0F2A3D',
  magenta: '#B3246B',
  amber: '#E0A526',
  teal: '#2E7F8C',
  slate: '#8FA3AD',
  paper: '#FFFFFF',
}

export const TRACK_PALETTE = [
  '#B3246B', '#1F6F8B', '#C98600', '#3A7D44', '#7B4FA0', '#C2452D',
  '#2A9D8F', '#8C6D1F', '#4361A8', '#A33B7A', '#5B8C2A', '#B5651D',
]

const kindIs = (k: string): ExpressionSpecification => ['==', ['get', 'kind'], k]

// Màu theo thứ tự tàu (color_index) xoay vòng trong bảng màu
const TRACK_COLOR = [
  'match',
  ['%', ['get', 'color_index'], TRACK_PALETTE.length],
  ...TRACK_PALETTE.flatMap((c, i) => [i, c]),
  TRACK_PALETTE[0],
] as unknown as ExpressionSpecification

function styleLayers(layer: MapLayer, source: string): LayerSpecification[] {
  const id = (s: string) => `${layer.id}:${s}`
  switch (layer.kind) {
    case 'position':
      return [
        { id: id('ref'), type: 'circle', source, filter: kindIs('reference'),
          paint: { 'circle-radius': 4, 'circle-color': COLORS.slate, 'circle-stroke-color': COLORS.paper, 'circle-stroke-width': 1.5 } },
        { id: id('pos-halo'), type: 'circle', source, filter: kindIs('position'),
          paint: { 'circle-radius': 14, 'circle-color': COLORS.magenta, 'circle-opacity': 0.15 } },
        { id: id('pos'), type: 'circle', source, filter: kindIs('position'),
          paint: { 'circle-radius': 6.5, 'circle-color': COLORS.magenta, 'circle-stroke-color': COLORS.paper, 'circle-stroke-width': 2 } },
      ]
    case 'track':
      return [
        { id: id('line-casing'), type: 'line', source, filter: kindIs('track'),
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: { 'line-color': COLORS.paper, 'line-width': 6, 'line-opacity': 0.9 } },
        { id: id('line'), type: 'line', source, filter: kindIs('track'),
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: { 'line-color': COLORS.magenta, 'line-width': 3 } },
        { id: id('start'), type: 'circle', source, filter: kindIs('track_start'),
          paint: { 'circle-radius': 5.5, 'circle-color': COLORS.ink, 'circle-stroke-color': COLORS.paper, 'circle-stroke-width': 2 } },
        { id: id('end'), type: 'circle', source, filter: kindIs('track_end'),
          paint: { 'circle-radius': 5.5, 'circle-color': COLORS.paper, 'circle-stroke-color': COLORS.magenta, 'circle-stroke-width': 3 } },
      ]
    case 'gaps':
      return [
        { id: id('link'), type: 'line', source, filter: kindIs('gap_link'),
          paint: { 'line-color': COLORS.amber, 'line-width': 2.5, 'line-dasharray': [2, 2] } },
        { id: id('lost'), type: 'circle', source, filter: kindIs('gap_start'),
          paint: { 'circle-radius': 6, 'circle-color': COLORS.amber, 'circle-stroke-color': COLORS.ink, 'circle-stroke-width': 1.5 } },
        { id: id('back'), type: 'circle', source, filter: kindIs('gap_end'),
          paint: { 'circle-radius': 6, 'circle-color': COLORS.teal, 'circle-stroke-color': COLORS.paper, 'circle-stroke-width': 1.5 } },
      ]
    case 'tracks':
      return [
        { id: id('lines'), type: 'line', source, filter: kindIs('track'),
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: {
            'line-color': TRACK_COLOR,
            'line-width': ['interpolate', ['linear'], ['zoom'], 4, 1.2, 9, 2.6],
            'line-opacity': 0.85,
          } },
      ]
  }
}

const LABELS: Record<string, string> = {
  position: 'Vị trí',
  reference: 'Điểm AIS gần nhất',
  track_start: 'Điểm đầu',
  track_end: 'Điểm cuối',
  gap_start: 'Mất tín hiệu',
  gap_end: 'Có tín hiệu lại',
  gap_link: 'Khoảng mất tín hiệu',
  track: 'Hành trình',
}

function popupHtml(f: MapGeoJSONFeature): string {
  const p = f.properties as Record<string, string | number | undefined>
  const rows: [string, unknown][] = [
    ['Tàu', p.name ?? p.label],
    ['Thời điểm', p.ts],
    ['Kéo dài', p.duration],
    ['Quãng đường', p.distance_nm !== undefined ? `${p.distance_nm} hải lý` : undefined],
    ['Số điểm', p.point_count],
    ['Tốc độ TB', p.avg_speed_knots !== undefined && p.avg_speed_knots !== null ? `${p.avg_speed_knots} hl/giờ` : undefined],
    ['Cách xác định', p.method === 'interpolated' ? 'nội suy' : p.method === 'last' ? 'điểm cuối cùng' : p.method],
  ]
  const esc = (v: unknown) => String(v).replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`)
  const body = rows
    .filter(([, v]) => v !== undefined && v !== null && v !== '' && v !== 'null')
    .map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`)
    .join('')
  return `<strong>${LABELS[String(p.kind)] ?? ''}</strong><dl>${body}</dl>`
}

interface Props {
  layers: MapLayer[]
  fitTo: { id: string; nonce: number } | null
}

export function MapView({ layers, fitTo }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const added = useRef(new Map<string, string[]>())
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (!container.current || mapRef.current) return
    const map = new MapLibreMap({
      container: container.current,
      style: STYLE_URL,
      bounds: INITIAL_BOUNDS,
      fitBoundsOptions: { padding: 24 },
      attributionControl: { compact: true },
    })
    map.addControl(new NavigationControl({ showCompass: false }), 'top-left')
    map.addControl(new ScaleControl({ unit: 'nautical' }), 'bottom-right')
    map.on('load', () => {
      // Container có thể chưa có kích thước lúc khởi tạo → đo lại rồi mới căn khung vùng dữ liệu
      map.resize()
      map.fitBounds(INITIAL_BOUNDS, { padding: 24, animate: false })
      setReady(true)
    })
    const observer = new ResizeObserver(() => map.resize())
    observer.observe(container.current)
    mapRef.current = map
    if (import.meta.env.DEV) (window as unknown as { __map: MapLibreMap }).__map = map
    const tracked = added.current
    return () => {
      observer.disconnect()
      map.remove()
      mapRef.current = null
      tracked.clear()
      setReady(false)
    }
  }, [])

  // Đồng bộ các lớp dữ liệu với bản đồ
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const wanted = new Set(layers.map((l) => l.id))
    for (const [id, ids] of added.current) {
      if (!wanted.has(id)) {
        ids.forEach((lid) => map.getLayer(lid) && map.removeLayer(lid))
        if (map.getSource(id)) map.removeSource(id)
        added.current.delete(id)
      }
    }
    for (const layer of layers) {
      if (!added.current.has(layer.id)) {
        map.addSource(layer.id, { type: 'geojson', data: layer.geojson })
        const specs = styleLayers(layer, layer.id)
        specs.forEach((spec) => map.addLayer(spec))
        const ids = specs.map((s) => s.id)
        added.current.set(layer.id, ids)
        ids.filter((lid) => !lid.endsWith('halo') && !lid.endsWith('casing')).forEach((lid) => {
          map.on('click', lid, (e: MapLayerMouseEvent) => {
            const f = e.features?.[0]
            if (f) new Popup({ closeButton: true, maxWidth: '260px' }).setLngLat(e.lngLat).setHTML(popupHtml(f)).addTo(map)
          })
          map.on('mouseenter', lid, () => (map.getCanvas().style.cursor = 'pointer'))
          map.on('mouseleave', lid, () => (map.getCanvas().style.cursor = ''))
        })
      }
      for (const lid of added.current.get(layer.id) ?? []) {
        map.setLayoutProperty(lid, 'visibility', layer.visible ? 'visible' : 'none')
      }
    }
  }, [layers, ready])

  // Zoom tới lớp vừa thêm
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || !fitTo) return
    const layer = layers.find((l) => l.id === fitTo.id)
    if (!layer?.bbox) return
    const [x0, y0, x1, y1] = layer.bbox
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    // Chừa chỗ cho ô chú giải nằm ở góc dưới bên trái bản đồ
    const legend = container.current?.parentElement?.querySelector<HTMLElement>('.legend')
    const padding = { top: 50, right: 50, left: 60, bottom: 40 + (legend?.offsetHeight ?? 0) }
    if (x1 - x0 < 0.02 && y1 - y0 < 0.02) {
      map.flyTo({ center: [x0, y0], zoom: 8, padding, animate: !reduce })
    } else {
      map.fitBounds([x0, y0, x1, y1], { padding, maxZoom: 9, animate: !reduce })
    }
    // chỉ chạy khi có yêu cầu zoom mới
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitTo, ready])

  return <div ref={container} className="map" role="region" aria-label="Bản đồ vị trí và hành trình tàu" />
}
