// Bộ icon nét (24×24) vẽ tay, tránh thêm thư viện
const PATHS = {
  ship: 'M3 16l2.2 4h13.6L21 16M5 16v-5h14v5M8 11V7h8v4M12 7V3.5',
  pin: 'M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 1113 0c0 5.4-6.5 11-6.5 11zM12 12.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5z',
  route: 'M6 20a2 2 0 100-4 2 2 0 000 4zM18 8a2 2 0 100-4 2 2 0 000 4zM6 16V10a4 4 0 014-4h6M18 8v6a4 4 0 01-4 4H8',
  signalOff: 'M3 3l18 18M8.6 16.4a4.8 4.8 0 016.3-.4M5.2 13a9.6 9.6 0 014.6-2.6M18.8 13a9.6 9.6 0 00-2.4-1.7M2 9.3a14.4 14.4 0 015-3M12 20h.01',
  company: 'M4 21V6l8-3v18M12 9h8v12M3 21h18M8 8v.01M8 12v.01M8 16v.01M16 13v.01M16 17v.01',
  fleet: 'M4 6h16M4 12h16M4 18h10',
  layers: 'M12 3l9 5-9 5-9-5 9-5zM3 12.5l9 5 9-5M3 17l9 5 9-5',
  send: 'M5 12h13M12 5l7 7-7 7',
  stop: 'M7 7h10v10H7z',
  plus: 'M12 5v14M5 12h14',
  close: 'M6 6l12 12M18 6L6 18',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  search: 'M10.5 18a7.5 7.5 0 100-15 7.5 7.5 0 000 15zM16 16l5 5',
  trash: 'M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3',
  eye: 'M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12zM12 15a3 3 0 100-6 3 3 0 000 6z',
  eyeOff: 'M3 3l18 18M10.6 5.1A10.7 10.7 0 0112 5c6.4 0 10 7 10 7a17 17 0 01-3.2 4.1M6.6 6.6C3.8 8.3 2 12 2 12s3.6 7 10 7a9.6 9.6 0 005.4-1.6M9.9 9.9a3 3 0 004.2 4.2',
  memory: 'M3 12a9 9 0 109-9 9.3 9.3 0 00-6.4 2.6L3 8M3 3v5h5M12 7.5V12l3 2',
  focus: 'M12 3v3M12 18v3M3 12h3M18 12h3M12 16a4 4 0 100-8 4 4 0 000 8z',
  alert: 'M12 9v4M12 17h.01M10.3 3.9L2.2 18a2 2 0 001.7 3h16.2a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z',
  compass: 'M12 22a10 10 0 100-20 10 10 0 000 20zM15.5 8.5l-2 5-5 2 2-5 5-2z',
  menu: 'M4 7h16M4 12h16M4 17h16',
  book: 'M4 5.5A2.5 2.5 0 016.5 3H20v15H6.5A2.5 2.5 0 004 20.5v-15zM4 20.5A2.5 2.5 0 006.5 23H20v-5M8 7h8M8 11h6',
  shield: 'M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6l8-3zM9 12l2 2 4-4',
  database: 'M12 3c4.4 0 8 1.3 8 3s-3.6 3-8 3-8-1.3-8-3 3.6-3 8-3zM4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6',
  chevron: 'M9 6l6 6-6 6',
  chart: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
  lock: 'M6 11h12v10H6zM8.5 11V7.5a3.5 3.5 0 017 0V11M12 15v2',
  logout: 'M15 4h3a2 2 0 012 2v12a2 2 0 01-2 2h-3M10 17l-5-5 5-5M5 12h11',
  user: 'M12 12a4 4 0 100-8 4 4 0 000 8zM4.5 20a7.5 7.5 0 0115 0',
  chat: 'M21 12a8 8 0 01-11.6 7.1L4 20.5l1.4-4.6A8 8 0 1121 12z',
  refresh: 'M20 11a8 8 0 00-14.6-4.5L4 8M4 3v5h5M4 13a8 8 0 0014.6 4.5L20 16M20 21v-5h-5',
  clock: 'M12 21a9 9 0 100-18 9 9 0 000 18zM12 7v5l3 2',
  coins: 'M9 11c3.9 0 7-1.3 7-3s-3.1-3-7-3-7 1.3-7 3 3.1 3 7 3zM2 8v4c0 1.7 3.1 3 7 3s7-1.3 7-3M2 12v4c0 1.7 3.1 3 7 3 1 0 2-.1 2.9-.3M16 12.5c3.3.3 6 1.4 6 2.8v.2M16 16.5c3.3-.2 6-1.3 6-2.7',
  cpu: 'M6 6h12v12H6zM9 9h6v6H9zM9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4',
  flask: 'M9 3h6M10 3v6L4.5 18.5A1.7 1.7 0 006 21h12a1.7 1.7 0 001.5-2.5L14 9V3M7.5 14h9',
} as const

export type IconName = keyof typeof PATHS

export function Icon({ name, size = 18, className }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d={PATHS[name]} />
    </svg>
  )
}

export function Spinner({ size = 16 }: { size?: number }) {
  return (
    <svg className="spinner" width={size} height={size} viewBox="0 0 24 24" aria-hidden>
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 00-9-9" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}
