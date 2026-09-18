// Đưa tài liệu tổng quan vào public/ để website phục vụ trực tiếp (file không commit hai lần)
import { copyFile, mkdir } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const files = [
  ['../../docs/VegaStar-Tong-quan.pdf', '../public/VegaStar-Tong-quan.pdf'],
  ['../../docs/images/ui-multi-tracks.png', '../public/pitch/img/demo-map.png'],
]

for (const [from, to] of files) {
  const target = resolve(here, to)
  try {
    await mkdir(dirname(target), { recursive: true })
    await copyFile(resolve(here, from), target)
  } catch (e) {
    console.warn('bỏ qua:', to, '—', e.message)
  }
}
console.log('đã sao chép tài liệu và ảnh cho website')
