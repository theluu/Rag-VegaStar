import { useId, useState, type FormEvent } from 'react'
import { ApiError, api } from '../lib/api'
import { saveSession } from '../lib/session'
import { Icon, Spinner } from './Icon'

// Gợi ý tài khoản cho môi trường demo (để trống khi không muốn hiện)
const LOGIN_HINT = (import.meta.env.VITE_LOGIN_HINT as string | undefined)?.trim()

function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 401) return 'Sai tên đăng nhập hoặc mật khẩu.'
    if (e.status === 429) return 'Bạn đã thử quá nhiều lần. Vui lòng đợi một phút rồi thử lại.'
    if (e.status === 404) return 'Máy chủ chưa bật đăng nhập (AUTH_USERS trống).'
    return `Không đăng nhập được (${e.status}). Vui lòng thử lại.`
  }
  return 'Không kết nối được máy chủ. Kiểm tra API rồi thử lại.'
}

export function LoginScreen({ notice }: { notice?: string | null }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const errorId = useId()

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password) {
      setError('Nhập tên đăng nhập và mật khẩu.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await api.login(username.trim(), password)
      saveSession({ token: res.token, username: res.username, expires_at: res.expires_at })
    } catch (err) {
      setError(errorText(err))
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login">
      <aside className="login-art">
        <svg className="login-chart" viewBox="0 0 600 800" preserveAspectRatio="xMidYMid slice" aria-hidden>
          <g stroke="#8fa9c0" strokeWidth="0.6" opacity="0.22">
            {Array.from({ length: 9 }, (_, i) => (
              <path key={`h${i}`} d={`M0 ${i * 100}H600`} />
            ))}
            {Array.from({ length: 7 }, (_, i) => (
              <path key={`v${i}`} d={`M${i * 100} 0V800`} />
            ))}
          </g>
          <path d="M40 690 C140 640 190 560 260 500 S390 390 430 300 S500 170 570 120" fill="none" stroke="#f07bb3" strokeWidth="2.2" />
          <path d="M60 760 C150 720 230 690 300 610 S420 520 520 470" fill="none" stroke="#8fd3d3" strokeWidth="1.4" />
          <path d="M430 300 L480 230" stroke="#f2a900" strokeWidth="2" strokeDasharray="6 5" />
          <circle cx="430" cy="300" r="5" fill="#f2a900" />
          <circle cx="480" cy="230" r="5" fill="#1f8a8a" />
          <circle cx="570" cy="120" r="7" fill="#0b2238" stroke="#f07bb3" strokeWidth="2.5" />
        </svg>
        <div className="login-brand">
          <svg viewBox="0 0 40 40" width="44" height="44" aria-hidden>
            <rect width="40" height="40" rx="10" fill="#B3246B" />
            <circle cx="20" cy="20" r="11" fill="none" stroke="#fff" strokeOpacity=".35" strokeWidth="1.5" />
            <path d="M20 7v26M7 20h26" stroke="#fff" strokeOpacity=".35" strokeWidth="1.2" />
            <path d="M20 11l4.5 9L20 29l-4.5-9z" fill="#fff" />
          </svg>
          <div>
            <strong>Hải đồ hỏi đáp</strong>
            <span>Tra cứu tàu biển bằng AI</span>
          </div>
        </div>
        <div className="login-pitch">
          <h2>Hỏi về tàu biển bằng tiếng Việt, nhận câu trả lời có chứng cứ và bản đồ.</h2>
          <ul>
            <li>Chủ sở hữu, vị trí, hành trình và các lần tắt AIS của 1.000 tàu</li>
            <li>Mỗi con số đều có mã chứng cứ truy về dữ liệu gốc</li>
            <li>Dữ liệu AIS 10–12/09/2026, vùng 102–118°E, 6–23°N</li>
          </ul>
          <a className="pitch-cta" href="/pitch/">
            Xem bản trình bày 6 slide
            <Icon name="chevron" size={16} />
          </a>
        </div>
      </aside>

      <main className="login-main">
        <form className="login-card" onSubmit={(e) => void submit(e)} noValidate aria-describedby={error ? errorId : undefined}>
          <div className="login-card-brand">
            <svg viewBox="0 0 40 40" width="36" height="36" aria-hidden>
              <rect width="40" height="40" rx="10" fill="#B3246B" />
              <path d="M20 11l4.5 9L20 29l-4.5-9z" fill="#fff" />
            </svg>
            <strong>Hải đồ hỏi đáp</strong>
          </div>
          <h1>Đăng nhập</h1>
          <p className="login-sub">Môi trường thử nghiệm chỉ dành cho người được cấp tài khoản.</p>

          {notice && !error && (
            <p className="login-notice" role="status">
              <Icon name="clock" size={16} />
              {notice}
            </p>
          )}
          {error && (
            <p className="login-error" id={errorId} role="alert">
              <Icon name="alert" size={16} />
              {error}
            </p>
          )}

          <label className="field">
            <span>Tên đăng nhập</span>
            <input
              name="username"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={busy}
              autoFocus
              required
            />
          </label>

          <label className="field">
            <span>Mật khẩu</span>
            <span className="password-wrap">
              <input
                name="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={busy}
                required
              />
              <button
                type="button"
                className="icon-button"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
                aria-pressed={showPassword}
              >
                <Icon name={showPassword ? 'eyeOff' : 'eye'} size={17} />
              </button>
            </span>
          </label>

          <button type="submit" className="login-submit" disabled={busy}>
            {busy ? <Spinner size={16} /> : <Icon name="lock" size={16} />}
            {busy ? 'Đang đăng nhập…' : 'Đăng nhập'}
          </button>

          {LOGIN_HINT && <p className="login-hint">{LOGIN_HINT}</p>}

          <div className="login-links">
            <span>Chưa có tài khoản? Xem trước sản phẩm:</span>
            <a className="login-link primary" href="/pitch/">
              <Icon name="chart" size={15} />
              Bản trình bày 6 slide
            </a>
            <a className="login-link" href="/VegaStar-Tong-quan.pdf">
              <Icon name="book" size={15} />
              Tài liệu tổng quan (PDF)
            </a>
            <a className="login-link" href="https://github.com/theluu/Rag-VegaStar" target="_blank" rel="noreferrer noopener">
              <Icon name="database" size={15} />
              Mã nguồn
            </a>
          </div>

          <p className="login-foot">Phiên đăng nhập tự hết hạn sau một thời gian. Không chia sẻ tài khoản.</p>
        </form>
      </main>
    </div>
  )
}
