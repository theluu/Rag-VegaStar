import { describe, expect, it } from 'vitest'
import { SseParser } from './sse'

describe('SseParser', () => {
  it('parses events split across arbitrary chunks', () => {
    const parser = new SseParser()
    const out = [
      ...parser.push('event: token\ndata: {"te'),
      ...parser.push('xt":"Xin "}\n\nevent: tok'),
      ...parser.push('en\r\ndata: {"text":"chào"}\r\n\r\n'),
    ]
    expect(out).toEqual([
      { event: 'token', data: { text: 'Xin ' } },
      { event: 'token', data: { text: 'chào' } },
    ])
  })

  it('ignores comments/pings and joins multi-line data', () => {
    const parser = new SseParser()
    const out = parser.push(': ping\n\nevent: done\ndata: {"a":\ndata: 1}\n\n')
    expect(out).toEqual([{ event: 'done', data: { a: 1 } }])
  })

  it('defaults event name to message and keeps incomplete tail', () => {
    const parser = new SseParser()
    expect(parser.push('data: {"x":2}\n\ndata: {"y"')).toEqual([{ event: 'message', data: { x: 2 } }])
    expect(parser.push(':3}\n\n')).toEqual([{ event: 'message', data: { y: 3 } }])
  })
})
