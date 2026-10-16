// The faint ash drifting behind Home (owner, 17 Oct 2026): specks of a token colour (home.css
// --home-ash) on one small canvas, drawn at 30 frames a second at most. It carries no data. The
// loop stops while the tab is hidden; under reduced motion it draws one still frame. A theme
// change redraws in the new colour.

const DENSITY = 1 / 9000; // specks per CSS px²
const FRAME_MS = 1000 / 30;

const rand = (a, b) => a + Math.random() * (b - a);

export function driftAsh(canvas) {
  const g = canvas.getContext("2d");
  if (!g) return;
  const still = window.matchMedia("(prefers-reduced-motion: reduce)");
  let specks = [];
  let w = 0;
  let h = 0;
  let colour = "";
  let raf = 0;
  let last = 0;

  function size() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = canvas.clientWidth;
    h = canvas.clientHeight;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = Math.round(w * h * DENSITY);
    specks = Array.from({ length: n }, () => ({
      x: rand(0, w), y: rand(0, h), r: rand(0.5, 1.6), a: rand(0.12, 0.5),
      vx: rand(-7, -2), vy: rand(2, 6), sway: rand(0, Math.PI * 2),
    }));
  }

  function draw() {
    g.clearRect(0, 0, w, h);
    if (!colour) return;
    g.fillStyle = colour;
    for (const s of specks) {
      g.globalAlpha = s.a;
      g.beginPath();
      g.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      g.fill();
    }
    g.globalAlpha = 1;
  }

  function move(dt) {
    for (const s of specks) {
      s.sway += dt * 0.4;
      s.x += (s.vx + Math.sin(s.sway) * 2) * dt;
      s.y += s.vy * dt;
      if (s.x < -4) s.x += w + 8;
      if (s.y > h + 4) s.y -= h + 8;
    }
  }

  function frame(now) {
    raf = requestAnimationFrame(frame);
    if (now - last < FRAME_MS) return;
    move(Math.min(now - last, 100) / 1000);
    last = now;
    draw();
  }

  function play() {
    cancelAnimationFrame(raf);
    raf = 0;
    if (still.matches || document.hidden) return draw();
    last = performance.now();
    raf = requestAnimationFrame(frame);
  }

  function readColour() {
    colour = getComputedStyle(canvas).getPropertyValue("--home-ash").trim();
    draw();
  }

  size();
  readColour();
  play();
  document.addEventListener("visibilitychange", play);
  still.addEventListener("change", play);
  window.matchMedia("(prefers-color-scheme: light)").addEventListener("change", readColour);
  new MutationObserver(readColour).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  let pending = 0;
  window.addEventListener("resize", () => {
    clearTimeout(pending);
    pending = setTimeout(() => { size(); draw(); }, 150);
  });
}
