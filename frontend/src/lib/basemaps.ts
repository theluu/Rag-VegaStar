// Các kiểu bản đồ nền. Style vector lấy từ OpenFreeMap (không cần khoá), ảnh vệ tinh từ Esri World Imagery.
import type { StyleSpecification } from 'maplibre-gl'

export const SATELLITE_HOST = 'https://server.arcgisonline.com'

const VECTOR_STYLE =
  (import.meta.env.VITE_MAP_STYLE_URL as string | undefined) || 'https://demotiles.maplibre.org/style.json'

/** Nền ảnh vệ tinh dựng thẳng bằng JSON style, không phụ thuộc file style bên ngoài. */
const SATELLITE_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    satellite: {
      type: 'raster',
      tiles: [`${SATELLITE_HOST}/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`],
      tileSize: 256,
      maxzoom: 18,
      attribution: 'Ảnh: Esri, Maxar, Earthstar Geographics',
    },
  },
  layers: [{ id: 'satellite', type: 'raster', source: 'satellite' }],
}

export type BasemapId = 'sang' | 'toi' | 've-tinh'

export interface Basemap {
  id: BasemapId
  label: string
  title: string
  style: string | StyleSpecification
  /** Style vector sáng được dịu màu nước/đất cho giống hải đồ */
  tint: boolean
  /** Nền tối/ảnh vệ tinh cần đường và nhãn sáng màu hơn */
  dark: boolean
}

export const BASEMAPS: Basemap[] = [
  { id: 'sang', label: 'Sáng', title: 'Bản đồ sáng (mặc định)', style: VECTOR_STYLE, tint: true, dark: false },
  {
    id: 'toi',
    label: 'Tối',
    title: 'Bản đồ nền tối, hợp khi xem nhiều hành trình',
    style: 'https://tiles.openfreemap.org/styles/dark',
    tint: false,
    dark: true,
  },
  { id: 've-tinh', label: 'Vệ tinh', title: 'Ảnh vệ tinh (Esri World Imagery)', style: SATELLITE_STYLE, tint: false, dark: true },
]

const KEY = 'vc.basemap'

export function loadBasemap(): BasemapId {
  try {
    const saved = localStorage.getItem(KEY)
    if (BASEMAPS.some((b) => b.id === saved)) return saved as BasemapId
  } catch {
    // storage bị chặn → dùng mặc định
  }
  return 'sang'
}

export function saveBasemap(id: BasemapId): void {
  try {
    localStorage.setItem(KEY, id)
  } catch {
    // bỏ qua
  }
}

export const basemapById = (id: BasemapId): Basemap => BASEMAPS.find((b) => b.id === id) ?? BASEMAPS[0]
