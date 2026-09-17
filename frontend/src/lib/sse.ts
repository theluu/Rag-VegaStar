export interface SseEvent {
  event: string
  data: unknown
}

/** Bộ đọc Server-Sent Events tăng dần: nhận từng mảnh văn bản, trả các sự kiện đã hoàn chỉnh. */
export class SseParser {
  private buffer = ''

  push(chunk: string): SseEvent[] {
    this.buffer += chunk.replace(/\r\n/g, '\n')
    const events: SseEvent[] = []
    let sep = this.buffer.indexOf('\n\n')
    while (sep !== -1) {
      const block = this.buffer.slice(0, sep)
      this.buffer = this.buffer.slice(sep + 2)
      const parsed = parseBlock(block)
      if (parsed) events.push(parsed)
      sep = this.buffer.indexOf('\n\n')
    }
    return events
  }
}

function parseBlock(block: string): SseEvent | null {
  let event = 'message'
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith(':')) continue
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
  }
  if (data.length === 0) return null
  return { event, data: JSON.parse(data.join('\n')) }
}
