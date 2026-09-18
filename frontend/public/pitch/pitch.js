// Điều hướng slide: phím mũi tên, nút, chấm chỉ vị trí. CSP chặn script inline nên tách ra file này.
(() => {
  const deck = document.getElementById('deck')
  const slides = [...document.querySelectorAll('.slide')]
  const dots = document.getElementById('dots')
  const counter = document.getElementById('counter')
  if (!deck || slides.length === 0) return

  slides.forEach((slide, i) => {
    const dot = document.createElement('a')
    dot.href = `#${slide.id}`
    dot.setAttribute('aria-label', `Slide ${i + 1}`)
    dots.appendChild(dot)
  })

  let current = 0
  const setCurrent = (index) => {
    current = index
    counter.textContent = `${index + 1}/${slides.length}`
    ;[...dots.children].forEach((dot, i) => dot.setAttribute('aria-current', String(i === index)))
  }

  const go = (index) => {
    const next = Math.max(0, Math.min(slides.length - 1, index))
    slides[next].scrollIntoView({ behavior: 'smooth', block: 'start' })
    setCurrent(next)
  }

  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
      if (visible) setCurrent(slides.indexOf(visible.target))
    },
    { root: deck, threshold: [0.5] },
  )
  slides.forEach((s) => observer.observe(s))

  document.getElementById('prev').addEventListener('click', () => go(current - 1))
  document.getElementById('next').addEventListener('click', () => go(current + 1))
  document.addEventListener('keydown', (e) => {
    if (['ArrowDown', 'PageDown', ' '].includes(e.key)) { e.preventDefault(); go(current + 1) }
    if (['ArrowUp', 'PageUp'].includes(e.key)) { e.preventDefault(); go(current - 1) }
    if (e.key === 'Home') { e.preventDefault(); go(0) }
    if (e.key === 'End') { e.preventDefault(); go(slides.length - 1) }
  })
  setCurrent(0)
})()
