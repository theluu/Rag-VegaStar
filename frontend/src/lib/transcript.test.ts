import { describe, expect, it } from 'vitest'
import type { StoredMessage } from './api'
import { argChips, buildTurns, linkCitations } from './transcript'

const base = { tool_calls: null, tool_call_id: null, tool_name: null, meta: null, created_at: '' }

describe('buildTurns', () => {
  it('groups stored messages into turns with tool steps and results', () => {
    const messages: StoredMessage[] = [
      { ...base, id: 1, turn_no: 1, role: 'user', content: 'Tàu X ở đâu?' },
      {
        ...base, id: 2, turn_no: 1, role: 'assistant', content: '',
        tool_calls: [{ id: 'c1', function: { name: 'get_last_position', arguments: '{"vessel":"X"}' } }],
      },
      { ...base, id: 3, turn_no: 1, role: 'tool', content: '{"status":"ok","position":{}}', tool_call_id: 'c1' },
      {
        ...base, id: 4, turn_no: 1, role: 'assistant', content: 'Ở đây [E1].',
        meta: {
          data_ids: ['d1'],
          evidence: [{ id: 'E1', tool: 'get_last_position', label: 'Vị trí cuối cùng X', ok: true, query: {}, sources: ['ais_positions'], facts: [], data_ids: ['d1'] }],
          verification: { numbers_checked: 0, ungrounded_numbers: [], citations: ['E1'], unknown_citations: [], evidence_count: 1, grounded: true },
        },
      },
      { ...base, id: 5, turn_no: 2, role: 'user', content: 'Còn nữa?' },
      { ...base, id: 6, turn_no: 2, role: 'assistant', content: '', meta: { error: 'RuntimeError' } },
    ]
    const turns = buildTurns(messages)
    expect(turns).toHaveLength(2)
    expect(turns[0].question).toBe('Tàu X ở đâu?')
    expect(turns[0].answer).toBe('Ở đây [E1].')
    expect(turns[0].evidence[0].id).toBe('E1')
    expect(turns[0].verification?.grounded).toBe(true)
    expect(turns[0].mapIds).toEqual(['d1'])
    expect(turns[0].steps).toEqual([
      { id: 'c1', name: 'get_last_position', args: { vessel: 'X' }, ok: true, summary: { status: 'ok' }, evidenceId: 'E1' },
    ])
    expect(turns[1].error).toContain('RuntimeError')
  })

  it('marks failed tool results', () => {
    const turns = buildTurns([
      { ...base, id: 1, turn_no: 1, role: 'user', content: 'q' },
      { ...base, id: 2, turn_no: 1, role: 'assistant', content: '', tool_calls: [{ id: 'c', function: { name: 'get_track', arguments: '{}' } }] },
      { ...base, id: 3, turn_no: 1, role: 'tool', content: '{"error":"thiếu start"}', tool_call_id: 'c' },
    ])
    expect(turns[0].steps[0].ok).toBe(false)
  })
})

describe('argChips', () => {
  it('labels known arguments in Vietnamese and formats times', () => {
    expect(argChips({ vessel: 'A', role: 'operator', start: '2026-09-11T00:00:00Z', limit: null })).toEqual([
      { label: 'Tàu', value: 'A' },
      { label: 'Vai trò', value: 'nhà khai thác' },
      { label: 'Từ', value: '11/09 00:00' },
    ])
  })

  it('keeps raw text arguments', () => {
    expect(argChips('{bad')).toEqual([{ label: 'Tham số', value: '{bad' }])
  })
})

describe('linkCitations', () => {
  it('turns evidence markers into internal links', () => {
    expect(linkCitations('Cờ Singapore [E1]. Hai nguồn [E2, E3].')).toBe(
      'Cờ Singapore [E1](#evidence-E1). Hai nguồn [E2](#evidence-E2) [E3](#evidence-E3).',
    )
    expect(linkCitations('Mảng [1] không đổi')).toBe('Mảng [1] không đổi')
  })
})
