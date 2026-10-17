// The backdrop behind Home (owner, 17 Oct 2026): a field geologist's contour lines round a vent,
// low right, and faint drifting ash, both in token colours (home.css --home-contour,
// --home-contour-index, --home-ash) on one small canvas, drawn at 30 frames a second at most.
// Neither carries data. The loop stops while the tab is hidden; under reduced motion it draws one
// still frame. A theme change redraws in the new colours.

const DENSITY = 1 / 9000; // specks per CSS px²
const FRAME_MS = 1000 / 30;

const rand = (a, b) => a + Math.random() * (b - a);

// Nine contour rings round the vent, in CSS px from it ([index?, x0, y0, x1, y1, ...]); every
// third-ish ring is an index contour, a little heavier. The vent sits 370 px in from the right
// and 290 px up from the bottom (30 and 130 on phones), so the rings frame the five steps.
const CONTOURS = [
  [0, [54,0,57,7,58,14,56,21,51,26,45,31,38,33,30,35,24,37,18,39,12,40,6,42,0,42,-6,42,-12,40,-18,39,-24,37,-30,35,-38,33,-45,31,-51,26,-56,21,-58,14,-57,7,-54,0,-49,-6,-45,-11,-42,-16,-40,-20,-38,-26,-35,-32,-32,-37,-27,-41,-20,-44,-14,-45,-7,-46,0,-46,7,-46,14,-45,20,-44,27,-41,32,-37,35,-32,38,-26,40,-20,42,-16,45,-11,49,-6]],
  [0, [100,10,102,24,98,38,89,50,78,59,66,67,54,74,43,81,32,87,20,92,8,95,-5,96,-18,94,-30,92,-42,90,-55,89,-69,88,-83,86,-98,81,-110,73,-118,61,-120,48,-119,34,-115,21,-111,10,-108,-1,-108,-12,-108,-24,-108,-36,-104,-49,-96,-60,-86,-69,-73,-75,-59,-79,-46,-82,-32,-84,-18,-86,-4,-85,9,-81,21,-74,30,-65,37,-54,43,-44,49,-36,58,-29,68,-22,81,-14,92,-3]],
  [1, [138,20,132,40,122,58,110,74,98,89,86,104,74,118,60,131,42,141,23,148,3,151,-17,152,-36,153,-56,154,-77,157,-100,157,-123,154,-143,145,-158,129,-167,110,-169,88,-167,68,-165,51,-166,35,-170,20,-176,4,-182,-15,-184,-35,-180,-54,-170,-72,-156,-87,-139,-100,-120,-111,-101,-121,-80,-128,-58,-133,-36,-132,-15,-125,4,-113,19,-98,31,-83,42,-71,55,-62,72,-54,92,-46,112,-35,128,-19,137,0]],
  [0, [162,30,152,54,142,77,132,99,123,121,110,142,93,162,72,177,49,189,24,198,0,208,-26,219,-54,231,-85,241,-118,244,-151,239,-179,223,-198,198,-209,169,-214,139,-216,113,-219,91,-227,72,-239,52,-251,30,-259,6,-261,-20,-256,-44,-244,-68,-229,-90,-212,-112,-194,-132,-172,-152,-146,-168,-116,-176,-84,-177,-54,-168,-27,-154,-4,-138,18,-124,40,-115,65,-108,93,-101,122,-91,148,-74,165,-51,173,-24,170,4]],
  [0, [191,40,184,70,176,99,165,128,149,154,128,177,103,196,77,214,52,232,27,254,0,279,-33,304,-72,322,-115,330,-157,322,-193,300,-220,269,-239,234,-253,202,-267,174,-284,149,-303,126,-323,100,-338,71,-346,40,-344,8,-336,-23,-324,-53,-309,-82,-294,-112,-275,-141,-251,-168,-220,-188,-183,-199,-144,-200,-106,-192,-72,-182,-40,-174,-9,-171,26,-172,66,-174,108,-170,148,-157,180,-133,200,-100,207,-63,205,-26,198,8]],
  [0, [247,50,240,89,226,126,203,158,174,186,146,211,119,237,96,266,72,301,43,337,6,370,-40,392,-90,397,-139,385,-183,359,-219,328,-249,296,-278,269,-310,247,-345,225,-381,200,-411,169,-432,132,-442,91,-442,50,-436,9,-426,-30,-414,-70,-399,-109,-376,-146,-344,-176,-302,-197,-255,-206,-208,-205,-165,-200,-127,-199,-90,-204,-51,-217,-5,-233,47,-245,101,-245,150,-230,190,-200,216,-160,232,-116,240,-72,244,-30,247,10]],
  [1, [306,60,292,107,268,150,241,189,215,227,194,267,174,311,149,359,114,404,67,438,10,455,-50,451,-108,431,-158,402,-202,374,-243,352,-286,336,-334,323,-385,307,-434,283,-475,249,-505,207,-525,160,-537,110,-545,60,-548,8,-546,-45,-531,-97,-502,-143,-456,-179,-400,-200,-340,-210,-284,-212,-235,-214,-194,-225,-153,-246,-108,-273,-55,-298,4,-313,64,-312,120,-292,165,-258,201,-216,230,-172,256,-128,279,-83,298,-37,308,11]],
  [0, [334,70,322,123,310,174,303,229,298,288,287,353,262,417,218,471,156,506,81,517,5,507,-65,483,-126,456,-180,435,-232,422,-286,416,-345,408,-404,393,-458,367,-505,330,-545,286,-578,237,-610,186,-640,130,-663,70,-672,6,-661,-58,-627,-115,-572,-160,-506,-190,-440,-210,-381,-227,-332,-248,-288,-279,-242,-317,-189,-354,-126,-382,-58,-391,9,-379,69,-351,121,-312,166,-270,208,-228,249,-187,287,-143,318,-94,337,-41,341,15]],
  [0, [352,80,367,140,388,207,406,284,409,365,385,442,332,505,256,545,166,560,77,557,-5,544,-77,534,-144,529,-210,530,-279,528,-348,519,-414,497,-473,463,-525,420,-574,374,-621,326,-670,275,-717,217,-752,152,-766,80,-753,8,-714,-56,-657,-110,-596,-153,-540,-191,-494,-233,-456,-283,-417,-342,-367,-401,-303,-449,-226,-478,-144,-481,-64,-461,8,-427,72,-386,131,-345,186,-304,238,-261,283,-213,316,-157,335,-97,342,-36,345,22]]
];

export function driftAsh(canvas) {
  const g = canvas.getContext("2d");
  if (!g) return;
  const still = window.matchMedia("(prefers-reduced-motion: reduce)");
  let specks = [];
  let w = 0;
  let h = 0;
  let colour = "";
  let ashAlpha = 1;
  let contour = "";
  let contourIndex = "";
  let vent = [0, 0];
  let raf = 0;
  let last = 0;

  function size() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = canvas.clientWidth;
    h = canvas.clientHeight;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    vent = w <= 760 ? [w - 30, h - 130] : [w - 370, h - 290];
    const n = Math.round(w * h * DENSITY);
    specks = Array.from({ length: n }, () => ({
      x: rand(0, w), y: rand(0, h), r: rand(0.5, 1.6), a: rand(0.12, 0.5),
      vx: rand(-7, -2), vy: rand(2, 6), sway: rand(0, Math.PI * 2),
    }));
  }

  // each ring through the midpoints of its points, so the lines read hand-drawn, not faceted
  function rings() {
    g.lineJoin = "round";
    for (const [index, pts] of CONTOURS) {
      const stroke = index ? contourIndex : contour;
      if (!stroke) continue;
      g.strokeStyle = stroke;
      g.globalAlpha = index ? 0.4 : 0.7;
      g.lineWidth = index ? 1.2 : 1;
      const n = pts.length / 2;
      const x = (i) => vent[0] + pts[(i % n) * 2];
      const y = (i) => vent[1] + pts[(i % n) * 2 + 1];
      g.beginPath();
      g.moveTo((x(n - 1) + x(0)) / 2, (y(n - 1) + y(0)) / 2);
      for (let i = 0; i < n; i += 1) g.quadraticCurveTo(x(i), y(i), (x(i) + x(i + 1)) / 2, (y(i) + y(i + 1)) / 2);
      g.stroke();
    }
    g.globalAlpha = 1;
  }

  function draw() {
    g.clearRect(0, 0, w, h);
    rings();
    if (!colour) return;
    g.fillStyle = colour;
    for (const s of specks) {
      g.globalAlpha = s.a * ashAlpha;
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
    const css = getComputedStyle(canvas);
    colour = css.getPropertyValue("--home-ash").trim();
    ashAlpha = Number.parseFloat(css.getPropertyValue("--home-ash-alpha")) || 1;
    contour = css.getPropertyValue("--home-contour").trim();
    contourIndex = css.getPropertyValue("--home-contour-index").trim();
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
