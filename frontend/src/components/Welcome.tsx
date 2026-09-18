import { Icon, type IconName } from './Icon'
import { DemoScript, ResourceButtons } from './Resources'

const GROUPS: { icon: IconName; title: string; text: string; examples: string[] }[] = [
  {
    icon: 'ship',
    title: 'Hồ sơ và chủ sở hữu',
    text: 'Danh sách tàu, mã nhận dạng, cờ, kích thước, các công ty theo vai trò.',
    examples: [
      'Cho tôi thông tin về tàu KOTA GAYA.',
      'Hệ thống có bao nhiêu tàu? Kể tên các tàu cá.',
      'Pacific International Lines còn sở hữu những tàu nào?',
    ],
  },
  {
    icon: 'route',
    title: 'Vị trí và hành trình',
    text: 'Vị trí tại một thời điểm, đường đi, quãng đường, tốc độ.',
    examples: [
      'Lúc 21:00 ngày 11/09/2026 (UTC) tàu KOTA GAYA đang ở đâu?',
      'Tàu có MMSI 563240200 đã đi từ đâu đến đâu trong ngày 11/09/2026?',
    ],
  },
  {
    icon: 'signalOff',
    title: 'Mất tín hiệu AIS',
    text: 'Khi nào tắt, ở đâu, xuất hiện lại ở đâu, tốc độ lúc đó.',
    examples: ['Tàu nào mất tín hiệu AIS lâu nhất trong dữ liệu? Mất ở đâu và xuất hiện lại ở đâu?'],
  },
  {
    icon: 'fleet',
    title: 'Cả đội tàu trên bản đồ',
    text: 'Hành trình của mọi tàu thuộc một công ty hoặc một loại tàu.',
    examples: ['Hiển thị hành trình của tất cả tàu do Evergreen Marine Corp khai thác từ 10/09 đến hết 12/09/2026.'],
  },
]

export function Welcome({ onPick, disabled, llmAvailable = true }: { onPick: (q: string) => void; disabled: boolean; llmAvailable?: boolean }) {
  return (
    <div className="welcome">
      <h2>Hỏi về tàu biển bằng tiếng Việt</h2>
      <p className="welcome-lead">
        1.000 tàu trong vùng 102–118°E, 6–23°N, dữ liệu AIS từ 10 đến 12/09/2026. Mọi con số đều lấy từ dữ liệu;
        vị trí và hành trình tự hiện trên bản đồ.
      </p>
      {!llmAvailable && (
        <p className="welcome-warning" role="status">
          <Icon name="alert" size={16} />
          Chưa cấu hình dịch vụ AI nên phần hỏi đáp tạm nghỉ. Bản đồ, API dữ liệu và trang Thống kê vẫn dùng được.
        </p>
      )}
      <div className="welcome-groups">
        {GROUPS.map((g) => (
          <section key={g.title} className="welcome-group">
            <header>
              <span className="welcome-icon">
                <Icon name={g.icon} size={18} />
              </span>
              <div>
                <h3>{g.title}</h3>
                <p>{g.text}</p>
              </div>
            </header>
            <ul>
              {g.examples.map((q) => (
                <li key={q}>
                  <button type="button" onClick={() => onPick(q)} disabled={disabled}>
                    {q}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>

      <DemoScript onPick={onPick} disabled={disabled} />

      <section className="welcome-resources">
        <header>
          <h3>Tài liệu và công cụ kiểm chứng</h3>
          <p>Dành cho người đánh giá: hiểu hệ thống, tự kiểm tra số liệu và xem mã nguồn.</p>
        </header>
        <ResourceButtons />
      </section>
    </div>
  )
}
