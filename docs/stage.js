// Canvas stage: prompts travel toward the model, the shield decides. Every packet is a real decision.
const TAU = Math.PI * 2;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const lerp = (a, b, t) => a + (b - a) * t;

export class Stage {
  constructor(canvas, { lanes = 5, mini = false, onDecision = () => {}, onPick = () => {}, reduced = false } = {}) {
    this.c = canvas;
    this.ctx = canvas.getContext('2d');
    this.mini = mini;
    this.laneCount = lanes;
    this.onDecision = onDecision;
    this.onPick = onPick;
    this.reduced = reduced;
    this.items = [];
    this.idx = 0;
    this.pills = [];
    this.parts = [];
    this.rings = [];
    this.flashes = [];
    this.cells = [];
    this.acc = 0;
    this.speed = 1;
    this.playing = true;
    this.visible = true;
    this.count = { allow: 0, flag: 0, block: 0, miss: 0, falseAlarm: 0, total: 0 };
    this.nodePulse = 0;
    this.nodeWarn = 0;
    this.last = performance.now();
    this.running = false;
    this.refreshColors();
    this.resize();
    new ResizeObserver(() => this.resize()).observe(canvas);
    new IntersectionObserver((es) => { this.visible = es[0].isIntersecting; this.kick(); }, { threshold: 0.01 }).observe(canvas);
    document.addEventListener('visibilitychange', () => this.kick());
    canvas.addEventListener('pointerdown', (e) => this.pick(e));
    this.kick();
  }

  refreshColors() {
    const cs = getComputedStyle(document.documentElement);
    const g = (n) => cs.getPropertyValue(n).trim();
    this.col = { lime: g('--lime'), ember: g('--ember'), bone: g('--bone'), void: g('--void'), dim: g('--dim'), panel: g('--panel') };
  }

  setItems(items) { this.items = items; this.idx = 0; }
  setSpeed(s) { this.speed = s; }
  setPlaying(p) { this.playing = p; this.kick(); }
  reset() { this.pills = []; this.parts = []; this.rings = []; this.count = { allow: 0, flag: 0, block: 0, miss: 0, falseAlarm: 0, total: 0 }; this.draw(0); }

  resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const r = this.c.getBoundingClientRect();
    this.W = Math.max(1, r.width);
    this.H = Math.max(1, r.height);
    this.c.width = Math.round(this.W * dpr);
    this.c.height = Math.round(this.H * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.narrow = this.W < 560;
    this.k = clamp(this.W / 900, 0.62, 1.15);
    this.shX = this.W * (this.narrow ? 0.6 : 0.58);
    this.mX = this.W * (this.narrow ? 0.88 : 0.89);
    const top = this.mini ? 14 : 40;
    const bot = this.mini ? 14 : 30;
    this.cy = (top + this.H - bot) / 2;
    const n = this.mini ? 1 : this.narrow ? 4 : this.laneCount;
    this.lanes = Array.from({ length: n }, (_, i) => (n === 1 ? this.cy : lerp(top + 14, this.H - bot - 14, i / (n - 1))));
    const r0 = clamp((this.H - top - bot) / (this.mini ? 6 : 15), 7, 15);
    this.hexR = r0;
    this.cells = [];
    const step = r0 * 1.74;
    const rows = Math.floor((this.H - top - bot) / step);
    for (let col = 0; col < 2; col++) {
      for (let i = 0; i < rows; i++) {
        const y = top + (this.H - top - bot - (rows - 1) * step) / 2 + i * step + (col ? step / 2 : 0);
        if (y > this.H - bot + 2) continue;
        this.cells.push({ x: this.shX + (col ? r0 * 0.88 : -r0 * 0.88), y, e: 0, hue: 'ember' });
      }
    }
    this.draw(0);
  }

  kick() {
    if (this.running || !this.visible || document.hidden) return;
    this.running = true;
    this.last = performance.now();
    requestAnimationFrame((t) => this.frame(t));
  }

  frame(t) {
    if (!this.visible || document.hidden) { this.running = false; return; }
    const dt = Math.min(0.05, (t - this.last) / 1000);
    this.last = t;
    this.step(dt);
    this.draw(dt);
    if (this.playing || (this.mini && (this.pills.length || this.parts.length || this.rings.length || this.flashes.length))) requestAnimationFrame((n) => this.frame(n));
    else this.running = false;
  }

  chipFor(item) {
    if (item.typed) return 'you';
    if (this.mini || item.set == null) return '';
    const hit = item.rules && item.rules[0];
    if (hit) return hit.cat.slice(0, 9);
    return ({ hard_benign: 'quoted', dolly_benign: 'everyday', indist: 'dataset', deepset: 'deepset', spml: 'chatbot', spml_dev: 'chatbot', obfuscated: 'encoded', attacks: 'plain', indirect: 'document' })[item.set] || '';
  }

  textFor(item) {
    // phones: a category chip plus a few words, so a packet stays legible; wider screens show more of the prompt
    const max = this.mini ? 60 : this.narrow ? 13 : 34;
    let s = item.text.replace(/\s+/g, ' ').replace(/[​-‏⁠﻿]/g, '·').trim();
    if (s.length > max) s = s.slice(0, max - 1) + '…';
    return s;
  }

  inject(item) {
    // a typed or recorded item enters the lane; its fate is the decision attached to it
    const ctx = this.ctx;
    ctx.font = `500 ${Math.round(11 * this.k + 1)}px "JetBrains Mono", monospace`;
    const txt = this.textFor(item);
    const chip = this.narrow ? this.chipFor(item) : '';
    ctx.font = `600 ${Math.round(8.5 * this.k + 1)}px "JetBrains Mono", monospace`;
    const chipW = chip ? ctx.measureText(chip).width + 14 : 0;
    ctx.font = `500 ${Math.round(11 * this.k + 1)}px "JetBrains Mono", monospace`;
    const w = ctx.measureText(txt).width + 24 + chipW;
    // lane with the most free space at its left edge, so new packets do not land on top of older ones
    let lane = 0, best = -1;
    if (!this.mini) {
      for (let i = 0; i < this.lanes.length; i++) {
        const j = (i + this.idx) % this.lanes.length;
        const clear = Math.min(1e9, ...this.pills.filter((q) => q.lane === j).map((q) => q.x));
        if (clear > best) { best = clear; lane = j; }
      }
    }
    const y = this.lanes[lane] + (this.mini ? 0 : (Math.random() - 0.5) * 6);
    const vx = (this.mini ? 190 : 130) * this.k * (this.mini ? 1 : this.speed);
    const startX = this.narrow && !this.mini ? 4 : -w - 8;  // on phones a packet appears fully inside the lane instead of sliding in from off-screen
    const p = { lane, item, txt, chip, chipW, w, h: 24 * this.k + 2, x: this.reduced ? this.shX - w - 26 : startX, y, vx, state: 'approach', a: 1, rot: 0, t: 0, decided: false, born: 0 };
    this.pills.push(p);
    return p;
  }

  step(dt) {
    if (!this.playing && !this.mini) return;  // paused: everything freezes where it is
    if (this.playing && !this.mini && this.items.length) {
      this.acc += dt;
      const every = (this.reduced ? 1.6 : 0.95) / this.speed;
      if (this.acc >= every) {
        this.acc = 0;
        this.inject(this.items[this.idx % this.items.length]);
        this.idx++;
      }
    }
    const sx = this.shX - this.hexR * 2.3;
    for (const p of this.pills) {
      p.t += dt;
      p.born = Math.min(1, p.born + dt * 3);
      if (p.state === 'approach') {
        if (this.reduced) { this.decide(p); continue; }
        p.x += p.vx * dt;
        if (p.x + p.w >= sx) this.decide(p);
      } else if (p.state === 'pass') {
        p.x += p.vx * dt;
        if (p.x + p.w >= this.mX - 26 * this.k) {
          p.state = 'done';
          if (p.item.action === 'flag') this.nodeWarn = 1;
          this.nodePulse = 1;
        }
      } else if (p.state === 'bounce') {
        p.x += p.vx * dt;
        p.vx *= 0.985;
        p.rot = lerp(p.rot, p.rotTarget, 0.08);
        p.a -= dt * (this.reduced ? 0.7 : 0.9);
      }
      if (this.reduced && p.state !== 'approach') p.a -= dt * 0.6;
    }
    this.pills = this.pills.filter((p) => p.state !== 'done' && p.a > 0 && p.x > -p.w - 40);
    for (const q of this.parts) { q.x += q.vx * dt; q.y += q.vy * dt; q.vy += 120 * dt; q.a -= dt * 1.8; }
    this.parts = this.parts.filter((q) => q.a > 0);
    for (const f of this.flashes) f.t += dt;
    this.flashes = this.flashes.filter((f) => f.t < 0.35);
    for (const r of this.rings) { r.t += dt; }
    this.rings = this.rings.filter((r) => r.t < 0.8);
    for (const c of this.cells) c.e = Math.max(0, c.e - dt * 1.7);
    this.nodePulse = Math.max(0, this.nodePulse - dt * 2.2);
    this.nodeWarn = Math.max(0, this.nodeWarn - dt * 1.6);
  }

  decide(p) {
    p.decided = true;
    const it = p.item;
    const a = it.action;
    this.count.total++;
    this.count[a]++;
    const attack = it.label === 1;
    p.err = (attack && a === 'allow') ? 'MISSED' : (!attack && it.label === 0 && a === 'block') ? 'FALSE ALARM' : '';
    if (p.err === 'MISSED') this.count.miss++;
    if (p.err === 'FALSE ALARM') this.count.falseAlarm++;
    const impactY = p.y;
    const hue = a === 'allow' ? 'lime' : 'ember';
    for (const c of this.cells) {
      const d = Math.abs(c.y - impactY);
      const e = Math.exp(-(d * d) / (2 * (this.hexR * 3.2) ** 2));
      if (e > c.e) { c.e = e * (a === 'allow' ? 0.7 : 1); c.hue = hue; }
    }
    if (a === 'block') {
      p.state = 'bounce';
      p.vx = -Math.abs(p.vx) * (this.narrow ? 0.35 : 0.75);
      p.rotTarget = (Math.random() > 0.5 ? 1 : -1) * 0.16;
      if (!this.reduced) {
        this.rings.push({ x: this.shX - this.hexR * 1.2, y: impactY, t: 0 });
        this.flashes.push({ x: this.shX - this.hexR * 2.1, y: impactY, t: 0 });
        for (let i = 0; i < 9; i++) this.parts.push({ x: this.shX - this.hexR * 2, y: impactY, vx: -(30 + Math.random() * 130), vy: (Math.random() - 0.5) * 150, a: 1, r: 1 + Math.random() * 1.6 });
      }
    } else {
      p.state = 'pass';
    }
    if (this.reduced) { p.state = 'bounce'; p.vx = 0; p.rotTarget = 0; }  // reduced motion: the packet stays put and fades
    this.onDecision(it, this.count, this);
  }

  hexPath(x, y, r) {
    const c = this.ctx;
    c.beginPath();
    for (let i = 0; i < 6; i++) {
      const a = (i / 6) * TAU + Math.PI / 6;
      const px = x + Math.cos(a) * r, py = y + Math.sin(a) * r;
      i ? c.lineTo(px, py) : c.moveTo(px, py);
    }
    c.closePath();
  }

  rgba(hex, a) {
    const h = hex.replace('#', '');
    const n = parseInt(h.length === 3 ? h.split('').map((x) => x + x).join('') : h, 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  }

  draw() {
    const { ctx, W, H, col, k } = this;
    ctx.clearRect(0, 0, W, H);
    const mono = (s, w = 500) => `${w} ${Math.round(s)}px "JetBrains Mono", ui-monospace, monospace`;
    // rails
    ctx.strokeStyle = this.rgba(col.bone, 0.07);
    ctx.lineWidth = 1;
    for (const y of this.lanes) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(this.mX - 28 * k, y); ctx.stroke(); }
    // shield cells
    ctx.lineWidth = 1.4;
    for (const c of this.cells) {
      const base = col.bone;
      this.hexPath(c.x, c.y, this.hexR * 0.86);
      if (c.e > 0.03) {
        const hc = c.hue === 'lime' ? col.lime : col.ember;
        ctx.fillStyle = this.rgba(hc, c.e * 0.3);
        ctx.fill();
        ctx.strokeStyle = this.rgba(hc, 0.25 + c.e * 0.75);
      } else ctx.strokeStyle = this.rgba(base, 0.2);
      ctx.stroke();
    }
    ctx.font = mono(9 * k + 1);
    ctx.textAlign = 'center';
    ctx.fillStyle = this.rgba(col.bone, 0.5);
    if (!this.mini) ctx.fillText('SENTINEL', this.shX, 22);
    // model node
    const nr = (this.mini ? 15 : 22) * k;
    ctx.fillStyle = this.rgba(col.lime, 0.1 + this.nodePulse * 0.25);
    ctx.beginPath(); ctx.arc(this.mX, this.cy, nr + 8 + this.nodePulse * 8, 0, TAU); ctx.fill();
    if (this.nodeWarn > 0.02) { ctx.strokeStyle = this.rgba(col.ember, this.nodeWarn); ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(this.mX, this.cy, nr + 12, 0, TAU); ctx.stroke(); }
    ctx.fillStyle = col.lime;
    ctx.beginPath(); ctx.arc(this.mX, this.cy, nr, 0, TAU); ctx.fill();
    ctx.fillStyle = '#0a0b0d';
    ctx.font = mono(9 * k + 1, 700);
    ctx.fillText('LLM', this.mX, this.cy + 3.5);
    if (!this.mini) { ctx.font = mono(8.5 * k + 1); ctx.fillStyle = this.rgba(col.bone, 0.45); ctx.fillText('MODEL', this.mX, this.cy + nr + 18); }
    // impact flash at the contact point
    for (const f of this.flashes) {
      const u = f.t / 0.35, rad = (14 + u * 26) * k;
      const g = ctx.createRadialGradient(f.x, f.y, 0, f.x, f.y, rad);
      g.addColorStop(0, this.rgba('#ffffff', (1 - u) * 0.9));
      g.addColorStop(0.35, this.rgba(col.ember, (1 - u) * 0.7));
      g.addColorStop(1, this.rgba(col.ember, 0));
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(f.x, f.y, rad, 0, TAU); ctx.fill();
    }
    // rings and particles
    for (const r of this.rings) {
      const u = r.t / 0.8;
      ctx.strokeStyle = this.rgba(col.ember, (1 - u) * 0.8);
      ctx.lineWidth = 2 * (1 - u) + 0.5;
      ctx.beginPath(); ctx.arc(r.x, r.y, 8 + u * 70 * k, -1.2, 1.2); ctx.stroke();
    }
    for (const q of this.parts) { ctx.fillStyle = this.rgba(col.ember, Math.max(0, q.a)); ctx.beginPath(); ctx.arc(q.x, q.y, q.r, 0, TAU); ctx.fill(); }
    // pills
    ctx.textAlign = 'left';
    for (const p of this.pills) {
      const it = p.item;
      let stroke = this.rgba(col.bone, 0.75), fill = null, txt = col.bone;
      if (p.decided) {
        if (it.action === 'block') { stroke = col.ember; fill = this.rgba(col.ember, 0.16); txt = col.ember; }
        else { stroke = col.lime; fill = it.action === 'flag' ? null : this.rgba(col.lime, 0.1); txt = col.lime; }
        if (p.err) { stroke = col.ember; txt = col.ember; fill = this.rgba(col.ember, 0.1); }  // wrong calls are marked, never hidden
      }
      ctx.save();
      ctx.translate(p.x + p.w / 2, p.y);
      ctx.rotate(p.rot);
      ctx.globalAlpha = clamp(p.a, 0, 1) * (this.narrow ? p.born : 1);
      ctx.beginPath(); ctx.roundRect(-p.w / 2, -p.h / 2, p.w, p.h, p.h / 2);
      if (fill) { ctx.fillStyle = fill; ctx.fill(); }
      ctx.lineWidth = 1.3; ctx.strokeStyle = stroke;
      if (p.decided && (it.action === 'flag' || p.err === 'MISSED')) ctx.setLineDash([3, 3]);
      ctx.stroke(); ctx.setLineDash([]);
      let tx = -p.w / 2 + 12;
      if (p.chip) {
        ctx.font = mono(8.5 * k + 1, 700);
        ctx.fillStyle = this.rgba(txt, 0.22);
        ctx.beginPath(); ctx.roundRect(-p.w / 2 + 6, -p.h / 2 + 4, p.chipW - 4, p.h - 8, (p.h - 8) / 2); ctx.fill();
        ctx.fillStyle = txt;
        ctx.fillText(p.chip, -p.w / 2 + 12, 3.5);
        tx = -p.w / 2 + 6 + p.chipW;
      }
      ctx.font = mono(11 * k + 1);
      ctx.fillStyle = txt;
      ctx.fillText(p.txt, tx, 4);
      if (p.decided && !this.mini) {
        ctx.font = mono(8.5 * k + 1, p.err ? 700 : 500);
        const truth = it.label === 1 ? 'attack' : it.label === 0 ? 'benign' : '';
        const tag = p.err ? `${truth} · ${p.err}` : truth ? `${truth} · ${it.action === 'block' ? 'blocked' : it.action === 'flag' ? 'flagged' : 'passed'}` : it.action;
        ctx.fillStyle = p.err ? col.ember : this.rgba(col.bone, 0.5);
        ctx.fillText(tag, -p.w / 2 + 6, p.h / 2 + 12);
      }
      ctx.restore();
    }
  }

  pick(e) {
    // forgiving tap target: the packet nearest to the touch within 56 px, moving or not; the stream pauses on a pick
    const r = this.c.getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    let best = null, bd = 56;
    for (const p of this.pills) {
      const dx = Math.max(p.x - x, 0, x - (p.x + p.w)), dy = Math.max(Math.abs(y - p.y) - p.h / 2, 0);
      const d = Math.hypot(dx, dy);
      if (d < bd) { bd = d; best = p; }
    }
    if (best) { this.setPlaying(false); this.onPick(best.item); }
  }
}
