import { Icon, type IconName } from './Icon'

const GROUPS: { icon: IconName; title: string; text: string; examples: string[] }[] = [
  {
    icon: 'ship',
    title: 'Hồ sơ và chủ sở hữu',
    text: 'Mã nhận dạng, cờ, kích thước, các công ty theo vai trò.',
    examples: ['Cho tôi thông tin về tàu KOTA GAYA.', 'Pacific International Lines còn sở hữu những tàu nào?'],
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

export function Welcome({ onPick, disabled }: { onPick: (q: string) => void; disabled: boolean }) {
  return (
    <div className="welcome">
      <h2>Hỏi về tàu biển bằng tiếng Việt</h2>
      <p className="welcome-lead">
        1.000 tàu trong vùng 102–118°E, 6–23°N, dữ liệu AIS từ 10 đến 12/09/2026. Mọi con số đều lấy từ dữ liệu;
        vị trí và hành trình tự hiện trên bản đồ.
      </p>
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
    </div>
  )
}
