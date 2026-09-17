// Phiên đăng nhập giao diện: token từ POST /auth/login, lưu trong localStorage đến khi hết hạn

export interface Session {
  token: string
  username: string
  expires_at: string
}

const KEY = 'vc.session'
// Token server cấp chỉ gồm ký tự base64url và dấu chấm
const TOKEN_RE = /^[\w.-]+$/
type Listener = (session: Session | null) => void
const listeners = new Set<Listener>()

function isValid(s: Partial<Session> | null, now = Date.now()): s is Session {
  return !!s && typeof s.token === 'string' && TOKEN_RE.test(s.token) && typeof s.username === 'string' &&
    typeof s.expires_at === 'string' && Date.parse(s.expires_at) > now
}

export function loadSession(now = Date.now()): Session | null {
  try {
    const raw = localStorage.getItem(KEY)
    const parsed = raw ? (JSON.parse(raw) as Partial<Session>) : null
    if (isValid(parsed, now)) return parsed
    if (raw) localStorage.removeItem(KEY)
  } catch {
    // storage bị chặn hoặc dữ liệu hỏng → coi như chưa đăng nhập
  }
  return null
}

export function saveSession(session: Session): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(session))
  } catch {
    // không lưu được thì phiên chỉ sống trong tab hiện tại
  }
  memory = session
  listeners.forEach((l) => l(session))
}

export function clearSession(): void {
  try {
    localStorage.removeItem(KEY)
  } catch {
    // bỏ qua
  }
  memory = null
  listeners.forEach((l) => l(null))
}

let memory: Session | null = loadSession()

/** Token hiện tại (null nếu chưa đăng nhập hoặc đã hết hạn). */
export function currentToken(): string | null {
  if (memory && Date.parse(memory.expires_at) <= Date.now()) {
    clearSession()
  }
  return memory?.token ?? null
}

export function onSessionChange(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
