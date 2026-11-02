/**
 * Header mark inspired by the public Muse launch icon: a white rounded tile
 * and a black brush M. The stroke is original, not Meta's trademark path.
 * It draws on, holds, then draws again.
 */
const M_PATH = "M16 46c1-14 2-22 6-24 3 8 6 16 8 20 2-6 5-16 8-20 4 2 5 12 6 24";

function mount(canvas) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  let running = true;
  const path = new Path2D(M_PATH);
  let length = 140;
  try {
    const svgPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
    svgPath.setAttribute("d", M_PATH);
    length = svgPath.getTotalLength() || length;
  } catch (e) {
    length = 140;
  }

  function resize() {
    const css = Math.max(32, canvas.clientWidth || Number(canvas.getAttribute("width")) || 40);
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(css * dpr);
    canvas.height = Math.round(css * dpr);
  }

  function frame(now) {
    if (!running) return;
    requestAnimationFrame(frame);
    const w = canvas.width;
    const h = canvas.height;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const s = w / 64;
    ctx.setTransform(s, 0, 0, s, 0, 0);

    const t = now / 1000;
    const tilt = Math.sin(t * 0.8) * 0.04;
    ctx.translate(32, 32);
    ctx.rotate(tilt);
    ctx.translate(-32, -32);

    ctx.shadowColor = "rgba(17,17,17,0.16)";
    ctx.shadowBlur = 8;
    ctx.shadowOffsetY = 3;
    roundRect(ctx, 3, 3, 58, 58, 18);
    ctx.fillStyle = "#ffffff";
    ctx.fill();
    ctx.shadowColor = "transparent";
    ctx.lineWidth = 1;
    ctx.strokeStyle = "#e7e5e4";
    ctx.stroke();

    // Draw the M over ~1.1s, hold, then repeat.
    const cycle = 3.4;
    const u = (t % cycle) / cycle;
    const draw = u < 0.38 ? u / 0.38 : 1;
    ctx.save();
    ctx.lineWidth = 5.2;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = "#111111";
    ctx.setLineDash([length, length]);
    ctx.lineDashOffset = length * (1 - draw);
    ctx.stroke(path);
    ctx.restore();
  }

  resize();
  requestAnimationFrame(frame);
  document.addEventListener("visibilitychange", () => {
    const hidden = document.hidden;
    if (hidden) running = false;
    else if (!running) {
      running = true;
      requestAnimationFrame(frame);
    }
  });
  window.addEventListener("resize", resize);
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function boot() {
  document.querySelectorAll("canvas.muse-mark").forEach((canvas) => {
    if (canvas.dataset.ready === "1") return;
    canvas.dataset.ready = "1";
    mount(canvas);
  });
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
else boot();
