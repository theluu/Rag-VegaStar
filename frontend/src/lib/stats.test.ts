import { describe, expect, it } from 'vitest'
import { fillDays, fmtDateTime, fmtMs, fmtPercent, fmtUptime, fmtUsd, niceMax, todayIn } from './stats'

describe('fillDays', () => {
  const daily = [
    { day: '2026-09-15', turns: 3, blocked: 1, errors: 0, cost_usd: 0.004 },
    { day: '2026-09-17', turns: 5, blocked: 0, errors: 0, cost_usd: 0.007 },
  ]

  it('điền đủ các ngày trong khoảng 7 ngày', () => {
    const days = fillDays(daily, '7d', '2026-09-17')
    expect(days).toHaveLength(7)
    expect(days[0].day).toBe('2026-09-11')
    expect(days.at(-1)).toEqual(daily[1])
    expect(days.find((d) => d.day === '2026-09-16')?.turns).toBe(0)
  })

  it('"Toàn bộ" bắt đầu từ ngày đầu có dữ liệu', () => {
    const days = fillDays(daily, 'all', '2026-09-17')
    expect(days.map((d) => d.day)).toEqual(['2026-09-15', '2026-09-16', '2026-09-17'])
    expect(fillDays([], 'all', '2026-09-17')).toHaveLength(1)
  })
})

describe('định dạng', () => {
  it('chi phí nhỏ vẫn hiện chữ số có nghĩa', () => {
    expect(fmtUsd(0)).toBe('$0')
    expect(fmtUsd(0.00153)).toBe('$0.0015')
    expect(fmtUsd(0.0968)).toBe('$0.097')
    expect(fmtUsd(12.5)).toBe('$12.50')
    expect(fmtUsd(null)).toBe('—')
  })

  it('phần trăm, mili giây và thời gian chạy', () => {
    expect(fmtPercent(0.9841, 1)).toBe('98,4%')
    expect(fmtPercent(null)).toBe('—')
    expect(fmtMs(0.42)).toBe('0,4 ms')
    expect(fmtMs(2150)).toBe('2,2 s')
    expect(fmtDateTime(new Date(2026, 8, 17, 7, 5).toISOString())).toBe('17/09 07:05')
    expect(fmtDateTime(null)).toBe('—')
    const start = '2026-09-17T00:00:00Z'
    expect(fmtUptime(start, Date.parse('2026-09-17T00:05:00Z'))).toBe('5 phút')
    expect(fmtUptime(start, Date.parse('2026-09-18T02:00:00Z'))).toBe('1 ngày 2 giờ')
  })

  it('trục tròn và ngày theo múi giờ', () => {
    expect(niceMax(0)).toBe(4)
    expect(niceMax(63)).toBe(80)
    expect(niceMax(0.0097)).toBeCloseTo(0.01)
    expect(todayIn('Asia/Ho_Chi_Minh', new Date('2026-09-17T18:00:00Z'))).toBe('2026-09-18')
  })
})
