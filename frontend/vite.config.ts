import react from '@vitejs/plugin-react'
import { readdir, readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { defineConfig, loadEnv, type Plugin } from 'vite'

const TEXT_FILES = /\.(txt|xml|webmanifest)$/

/** Điền VITE_SITE_URL vào index.html và các file tĩnh SEO/GEO (robots, sitemap, llms.txt) khi build. */
function siteUrl(url: string): Plugin {
  let outDir = 'dist'
  return {
    name: 'site-url',
    configResolved(config) {
      outDir = config.build.outDir
    },
    transformIndexHtml(html) {
      return html.replaceAll('%VITE_SITE_URL%', url)
    },
    async closeBundle() {
      for (const name of await readdir(outDir)) {
        if (!TEXT_FILES.test(name)) continue
        const path = join(outDir, name)
        const text = await readFile(path, 'utf8')
        if (text.includes('%VITE_SITE_URL%')) await writeFile(path, text.replaceAll('%VITE_SITE_URL%', url))
      }
    },
  }
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const site = (env.VITE_SITE_URL || 'http://localhost:5173').replace(/\/$/, '')
  return {
    plugins: [react(), siteUrl(site)],
    server: { port: 5173 },
    worker: { format: 'es' },
    // maplibre-gl chiếm phần lớn bundle; chấp nhận một chunk lớn thay vì cảnh báo
    build: { chunkSizeWarningLimit: 1600 },
  }
})
