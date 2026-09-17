import { beforeEach, describe, expect, it, vi } from 'vitest'

function memoryStorage() {
  const data = new Map<string, string>()
  return {
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
  }
}

const future = () => new Date(Date.now() + 3_600_000).toISOString()

describe('session', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.stubGlobal('localStorage', memoryStorage())
  })

  it('lưu, đọc lại và báo thay đổi phiên', async () => {
    const s = await import('./session')
    const seen: (string | null)[] = []
    s.onSessionChange((v) => seen.push(v?.username ?? null))
    expect(s.currentToken()).toBeNull()

    s.saveSession({ token: 't1', username: 'demo', expires_at: future() })
    expect(s.currentToken()).toBe('t1')
    expect(s.loadSession()?.username).toBe('demo')

    s.clearSession()
    expect(s.currentToken()).toBeNull()
    expect(seen).toEqual(['demo', null])
  })

  it('bỏ phiên hết hạn hoặc dữ liệu hỏng', async () => {
    localStorage.setItem('vc.session', JSON.stringify({ token: 't', username: 'u', expires_at: '2000-01-01T00:00:00Z' }))
    const s = await import('./session')
    expect(s.loadSession()).toBeNull()
    expect(localStorage.getItem('vc.session')).toBeNull()

    localStorage.setItem('vc.session', JSON.stringify({ token: 'v1.giả.mạo', username: 'u', expires_at: future() }))
    expect(s.loadSession()).toBeNull()

    localStorage.setItem('vc.session', '{hỏng')
    expect(s.loadSession()).toBeNull()
  })

  it('token hết hạn trong lúc dùng thì tự xoá', async () => {
    const s = await import('./session')
    const listener = vi.fn()
    s.onSessionChange(listener)
    s.saveSession({ token: 't2', username: 'demo', expires_at: new Date(Date.now() + 50).toISOString() })
    vi.useFakeTimers({ now: Date.now() + 1000 })
    expect(s.currentToken()).toBeNull()
    expect(listener).toHaveBeenLastCalledWith(null)
    vi.useRealTimers()
  })
})
