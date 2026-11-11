/* Moteur de rendu « motion design » — déterministe.
 *
 * Principe : la page ne joue RIEN en temps réel. Python appelle init(timeline)
 * une fois, puis renderAt(t) pour chaque image (t en secondes) et prend une
 * capture. Le même t donne toujours la même image : pas de minuteur, pas de
 * hasard, pas de réseau.
 *
 * La « timeline » est produite par studio/timeline.py à partir du storyboard
 * (écrit par le LLM) et des horodatages de la voix.
 */
(function () {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const rich = s => esc(s).replace(/\*([^*]+)\*/g, '<em>$1</em>');        // *mot* -> italique couleur d'accent
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));

  const E = {
    lin: x => x,
    out: x => 1 - Math.pow(1 - x, 3),
    outExpo: x => (x >= 1 ? 1 : 1 - Math.pow(2, -10 * x)),
    inOut: x => (x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2),
    back: x => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); },
    in: x => x * x * x,
  };

  /* ------------------------------------------------------------------ */
  /* Interpolations : chaque élément a, par propriété, une liste d'étapes */
  /* ------------------------------------------------------------------ */
  const ITEMS = new Map();
  const TICK = [];
  function tw(elm, t0, d, props, ease) {
    let it = ITEMS.get(elm);
    if (!it) { it = { el: elm, p: {}, hidden: null }; ITEMS.set(elm, it); }
    for (const k in props) (it.p[k] = it.p[k] || []).push({ t0, d: Math.max(d, 1e-4), a: props[k][0], b: props[k][1], e: E[ease || 'out'] });
  }
  function val(list, t) {
    let cur = null;
    for (let i = 0; i < list.length; i++) { if (list[i].t0 <= t) cur = list[i]; else break; }
    if (!cur) return list[0].a;
    const x = (t - cur.t0) / cur.d;
    return x >= 1 ? cur.b : cur.a + (cur.b - cur.a) * cur.e(x);
  }
  function apply(it, t) {
    const p = it.p, s = it.el.style;
    const o = p.o ? val(p.o, t) : 1;
    if (o <= 0.002) { if (it.hidden !== true) { s.visibility = 'hidden'; it.hidden = true; } return; }
    if (it.hidden !== false) { s.visibility = ''; it.hidden = false; }
    s.opacity = o >= 0.999 ? '' : o.toFixed(3);
    const x = p.x ? val(p.x, t) : 0, y = p.y ? val(p.y, t) : 0, sc = p.s ? val(p.s, t) : 1, r = p.r ? val(p.r, t) : 0;
    s.transform = (x || y || r || sc !== 1) ? `translate(${x.toFixed(2)}px,${y.toFixed(2)}px) rotate(${r.toFixed(3)}deg) scale(${sc.toFixed(4)})` : '';
    const b = p.b ? val(p.b, t) : 0;
    s.filter = b > 0.05 ? `blur(${b.toFixed(2)}px)` : '';
    if (p.c) { const c = val(p.c, t); s.clipPath = c >= 99.9 ? '' : `inset(-30% ${(100 - c).toFixed(2)}% -30% -6%)`; }
  }
  const pop = (e, t, d = 0.38) => tw(e, t, d, { o: [0, 1], s: [0.86, 1], y: [16, 0], b: [8, 0] }, 'back');

  /* ------------------------------------------------------------------ */
  /* Mascotte originale en pixels + petits accessoires                    */
  /* ------------------------------------------------------------------ */
  const BODY = [
    '......D......',
    '......A......',
    '..AAAAAAAAA..',
    '.AAAAAAAAAAA.',
    '.AAAAAAAAAAA.',
    '.AA..AAA..AA.',
    '.AA..AAA..AA.',
    '.AAAAAAAAAAA.',
    '.AAAAAAAAAAA.',
    '..AAAAAAAAA..',
    '...AA...AA...',
    '..AAA...AAA..'];
  const ICONS = {
    screen: ['#######', '#.....#', '#.##..#', '#.....#', '#######', '..###..', '.#####.'],
    play:   ['#######', '#.#...#', '#.##..#', '#.###.#', '#.##..#', '#.#...#', '#######'],
    pencil: ['.....##', '....###', '...###.', '..###..', '.###...', '###....', '##.....'],
    cursor: ['#......', '##.....', '###....', '####...', '#####..', '##.#...', '#...#..'],
    bulb:   ['..###..', '.#...#.', '#..#..#', '#..#..#', '.#...#.', '..###..', '..###..'],
    star:   ['...#...', '...#...', '#######', '.#####.', '..###..', '.##.##.', '#.....#'],
    bolt:   ['...##..', '..##...', '.####..', '..##...', '.##....', '##.....', '#......'],
    coin:   ['.#####.', '#.....#', '#.###.#', '#.#...#', '#.###.#', '#.....#', '.#####.'],
    chat:   ['#######', '#.....#', '#.#.#.#', '#.....#', '#######', '.##....', '.#.....'],
    chart:  ['......#', '....#.#', '....#.#', '..#.#.#', '..#.#.#', '#.#.#.#', '#######'],
    rocket: ['...#...', '..###..', '..#.#..', '..###..', '.#####.', '#.###.#', '..#.#..'],
    check:  ['.......', '......#', '.....##', '#...##.', '##.##..', '.###...', '..#....'],
    gear:   ['.#.#.#.', '#######', '.##.##.', '##...##', '.##.##.', '#######', '.#.#.#.'],
  };
  function mascotSVG(px, icon, happy) {
    const W = 13 * px, H = 12 * px;
    let r = '';
    BODY.forEach((row, y) => [...row].forEach((ch, x) => {
      if (ch === 'A') r += `<rect x="${x * px}" y="${y * px}" width="${px + .5}" height="${px + .5}" fill="var(--accent)"/>`;
      if (ch === 'D') r += `<rect x="${x * px}" y="${y * px}" width="${px + .5}" height="${px + .5}" fill="var(--ink)"/>`;
    }));
    // reflet + yeux (groupe à part pour le clignement)
    r += `<rect x="${2 * px}" y="${2 * px}" width="${9 * px}" height="${px * .5}" fill="rgba(255,255,255,.22)"/>`;
    const eyes = happy
      ? `<path d="M${3 * px} ${6.6 * px} l${px} -${px} l${px} ${px} M${8 * px} ${6.6 * px} l${px} -${px} l${px} ${px}" stroke="var(--ink)" stroke-width="${px * .55}" fill="none" stroke-linecap="square"/>`
      : `<rect x="${3 * px}" y="${5 * px}" width="${2 * px}" height="${2 * px}" fill="var(--ink)"/><rect x="${8 * px}" y="${5 * px}" width="${2 * px}" height="${2 * px}" fill="var(--ink)"/>` +
        `<rect x="${3 * px}" y="${5 * px}" width="${px * .8}" height="${px * .8}" fill="#fff"/><rect x="${8 * px}" y="${5 * px}" width="${px * .8}" height="${px * .8}" fill="#fff"/>`;
    let ic = '';
    if (icon && ICONS[icon]) {
      const q = px * 0.62, ox = 9.6 * px, oy = -2.6 * px;
      ic += `<rect x="${ox - q}" y="${oy - q}" width="${9 * q}" height="${9 * q}" rx="${q * 1.2}" fill="#fff" stroke="var(--ink)" stroke-width="${q * .5}"/>`;
      ICONS[icon].forEach((row, y) => [...row].forEach((ch, x) => { if (ch === '#') ic += `<rect x="${ox + x * q}" y="${oy + y * q}" width="${q + .4}" height="${q + .4}" fill="var(--ink)"/>`; }));
    }
    return `<svg width="${W}" height="${H + px}" viewBox="0 0 ${W} ${H + px}"><ellipse cx="${W / 2}" cy="${H + px * .55}" rx="${px * 4.2}" ry="${px * .45}" fill="rgba(60,30,15,.16)"/>` +
      `<g class="mbody">${r}<g class="meyes" style="transform-origin:${6.5 * px}px ${6 * px}px">${eyes}</g></g><g class="micon">${ic}</g></svg>`;
  }

  const CHECK = '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="#fff" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const CROSS = '<svg viewBox="0 0 24 24"><path d="M6.5 6.5l11 11M17.5 6.5l-11 11" fill="none" stroke="#fff" stroke-width="3.6" stroke-linecap="round"/></svg>';
  const fmtInt = n => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0');

  /* ------------------------------------------------------------------ */
  /* Construction des blocs                                               */
  /* ------------------------------------------------------------------ */
  function buildBlock(b, col) {
    const at = b.at;
    if (b.kind === 'checklist' || b.kind === 'compare') {
      const card = el('div', 'card'); col.appendChild(card);
      if (b.label) card.appendChild(el('div', 'label', esc(b.label)));
      pop(card, at);
      (b.rows || []).forEach((row, i) => {
        const r = typeof row === 'string' ? { text: row, ok: true } : row;
        const rt = (b.rowAt && b.rowAt[i] != null) ? b.rowAt[i] : at + 0.25 + i * 0.3;
        const d = el('div', 'row' + (r.hot ? ' hot' : ''));
        d.innerHTML = `<span class="ix">${String(i + 1).padStart(2, '0')}</span><span class="tx">${rich(r.text)}</span><span class="ck${r.ok === false ? ' no' : ''}">${r.ok === false ? CROSS : CHECK}</span>`;
        card.appendChild(d);
        tw(d, rt, 0.24, { o: [0, 1], x: [-18, 0], b: [5, 0] });
        tw($('.ck', d), rt + 0.13, 0.3, { o: [0, 1], s: [0.2, 1] }, 'back');
      });
    } else if (b.kind === 'stat') {
      const card = el('div', 'card stat'); col.appendChild(card);
      if (b.label) card.appendChild(el('div', 'label', esc(b.label)));
      const big = el('div', 'big'); card.appendChild(big);
      const hasNum = typeof b.value === 'number' && isFinite(b.value);
      big.innerHTML = `<span class="v">${hasNum ? fmtInt(b.value) : esc(b.value)}</span>${esc(b.suffix || '')}<span class="u">${esc(b.unit || '')}</span>`;
      pop(card, at);
      if (hasNum) {
        const v = $('.v', big), t0 = at + 0.04, d = 0.75, dec = (String(b.value).split('.')[1] || '').length;
        TICK.push(t => {
          const x = E.out(clamp((t - t0) / d)); const n = b.value * x;
          const txt = dec ? n.toFixed(dec).replace('.', ',') : fmtInt(n);
          if (v.textContent !== txt) v.textContent = txt;
        });
      }
    } else if (b.kind === 'pill') {
      const w = el('div', 'pillwrap'); const p = el('div', 'pill', rich(b.text)); w.appendChild(p); col.appendChild(w); pop(p, at, 0.34);
    } else if (b.kind === 'terminal') {
      const card = el('div', 'card term'); col.appendChild(card);
      card.innerHTML = `<div class="bar"><span class="dot" style="background:#EC6A5E"></span><span class="dot" style="background:#F4BF4F"></span><span class="dot" style="background:#61C554"></span><span style="margin-left:10px">${esc(b.label || 'terminal')}</span></div><div class="cmd">&gt; <span class="ty"></span><span class="caret"></span></div>`;
      pop(card, at);
      const ty = $('.ty', card), caret = $('.caret', card), txt = String(b.text || ''), t0 = at + 0.3, d = Math.min(1.1, 0.045 * txt.length + 0.2);
      TICK.push(t => {
        const n = Math.round(clamp((t - t0) / d) * txt.length); const cur = txt.slice(0, n);
        if (ty.textContent !== cur) ty.textContent = cur;
        caret.style.opacity = (Math.floor(t * 2.5) % 2 === 0 || (t > t0 && t < t0 + d)) ? 1 : 0;
      });
    } else if (b.kind === 'chips') {
      const w = el('div', 'chips'); col.appendChild(w);
      (b.items || []).forEach((c, i) => {
        const ch = el('div', 'chip', rich(c)); w.appendChild(ch);
        pop(ch, (b.itemAt && b.itemAt[i] != null) ? b.itemAt[i] : at + i * 0.22, 0.34);
      });
    } else if (b.kind === 'note') {
      const card = el('div', 'card note', rich(b.text)); col.appendChild(card); pop(card, at);
    }
  }

  function fitWidth(e, maxW, min = 0.45) {
    if (!e) return 1; let fs = parseFloat(getComputedStyle(e).fontSize), k = 1, guard = 40;
    while (e.scrollWidth > maxW + 0.5 && k > min && guard--) { k -= 0.03; e.style.fontSize = (fs * k).toFixed(1) + 'px'; }
    return k;
  }

  /* ------------------------------------------------------------------ */
  let TL = null, DUR = 0;
  window.init = async function (tl) {
    TL = tl; DUR = tl.duration;
    const th = tl.theme || {}, root = document.documentElement.style;
    for (const k in th) root.setProperty('--' + k, th[k]);
    await Promise.all(['800 60px "Inter Tight"', '900 60px "Inter Tight"', '700 60px "Inter Tight"', 'italic 60px "Instrument Serif"', '400 20px "JetBrains Mono"', '700 20px "JetBrains Mono"', '600 60px "Caveat"'].map(f => document.fonts.load(f)));
    await document.fonts.ready;
    const report = { warnings: [] };
    const scenesRoot = $('#scenes');
    const cueTimes = [];

    tl.scenes.forEach((sc, idx) => {
      const first = idx === 0, last = idx === tl.scenes.length - 1, t0 = sc.t0, t1 = sc.t1;
      const root = el('div', 'scene ' + sc.type); scenesRoot.appendChild(root);
      if (first) tw(root, 0, 0.13, { o: [0.7, 1], b: [5, 0] });
      else tw(root, t0, 0.24, { o: [0, 1], b: [14, 0], s: [1.014, 1] });
      if (!last) tw(root, t1 - 0.13, 0.13, { o: [1, 0], b: [0, 14], s: [1, 0.986] }, 'in');

      if (sc.type === 'hook') {
        if (sc.kicker) { const k = el('div', 'kicker', `<span>${esc(sc.kicker)}</span>`); root.appendChild(k); if (!first) pop(k, t0 + 0.05); }
        const head = el('div', 'head', `<div class="ttl">${rich(sc.title)}</div>`); root.appendChild(head);
        const col = el('div', 'col'); root.appendChild(col);
        const cu = sc.cues || {};
        if (sc.chips && sc.chips.length) {
          const g = el('div', 'grid2'); col.appendChild(g);
          const c0 = cu.chips != null ? cu.chips : t0 + 0.55;
          sc.chips.forEach((c, i) => {
            const ch = el('div', 'chip', `<span class="n">${i + 1}</span><span class="t">${rich(c)}</span>`); g.appendChild(ch);
            pop(ch, c0 + i * (sc.chips.length > 6 ? 0.07 : 0.1), 0.34);
          });
          if (sc.chips.length % 2 === 1) g.lastChild.style.gridColumn = '1 / span 2';
        }
        if (sc.stamp) {
          const w = el('div', 'stampwrap'); const s = el('div', 'stamp', esc(sc.stamp)); w.appendChild(s); col.appendChild(w);
          const ts = cu.stamp != null ? cu.stamp : t0 + 1.6; cueTimes.push(ts);
          tw(s, ts, 0.3, { o: [0, 1], s: [2.1, 1], r: [-16, -5], b: [6, 0] }, 'outExpo');
          tw(col, ts + 0.02, 0.12, { s: [1, 0.985] }, 'out'); tw(col, ts + 0.14, 0.3, { s: [0.985, 1] }, 'back');
        }
        if (sc.pill) {
          const w = el('div', 'pillwrap'); const p = el('div', 'pill', rich(sc.pill)); w.appendChild(p); col.appendChild(w);
          const tp = cu.pill != null ? cu.pill : t0 + 2.6; cueTimes.push(tp); pop(p, tp, 0.34);
        }
        fitWidth($('.ttl', head), 960);
        root.querySelectorAll('.grid2 .chip').forEach(c => fitWidth($('.t', c), $('.t', c).clientWidth || 300, 0.6));
      }

      else if (sc.type === 'section') {
        const head = el('div', 'head', `${sc.n != null ? `<div class="num">${esc(sc.n)}</div>` : ''}<div class="ttl">${rich(sc.title)}</div>`);
        root.appendChild(head);
        if ($('.num', head)) tw($('.num', head), t0 + 0.06, 0.4, { s: [0.3, 1], o: [0, 1], r: [-40, 0] }, 'back');
        const col = el('div', 'col'); root.appendChild(col);
        (sc.blocks || []).forEach(b => {
          buildBlock(b, col); cueTimes.push(b.at);
          (b.rowAt || b.itemAt || []).forEach(x => cueTimes.push(x));
        });
        // ajustements de largeur
        const ttl = $('.ttl', head); let guard = 40, k = 1, fs = parseFloat(getComputedStyle(ttl).fontSize);
        while (head.scrollWidth > head.clientWidth + 0.5 && k > 0.5 && guard--) { k -= 0.03; ttl.style.fontSize = (fs * k).toFixed(1) + 'px'; }
        col.querySelectorAll('.row .tx').forEach(e => fitWidth(e, e.clientWidth, 0.55));
        col.querySelectorAll('.stat .big').forEach(e => fitWidth(e, 872, 0.4));
        const terms = sc.blocks.filter(b => b.kind === 'terminal');
        col.querySelectorAll('.term .cmd').forEach((e, i) => { const ty = $('.ty', e), full = terms[i]; if (full) { ty.textContent = full.text; fitWidth(e, e.clientWidth, 0.5); ty.textContent = ''; } });
        col.querySelectorAll('.pill, .chip').forEach(e => fitWidth(e, 900, 0.5));
        const avail = 1226 - col.offsetTop;
        if (col.scrollHeight > avail) { const s = avail / col.scrollHeight; col.style.zoom = s.toFixed(3); report.warnings.push(`scène ${idx + 1} : contenu réduit à ${(s * 100).toFixed(0)} %`); }
      }

      else if (sc.type === 'cta') {
        if (tl.avatar) { const a = el('div', 'avatar'); a.style.backgroundImage = `url("${tl.avatar}")`; root.appendChild(a); pop(a, t0 + 0.12, 0.45); }
        const card = el('div', 'ctacard', `<div class="cta-word">${rich(sc.verb || 'Commente')}</div><div class="kw">“<span class="kwt"></span>”</div>`);
        root.appendChild(card);
        tw(card, t0 + 0.04, 0.5, { o: [0, 1], y: [80, 0], r: [-10, -3], b: [10, 0], s: [0.9, 1] }, 'back');
        const kwt = $('.kwt', card), kw = String(sc.keyword || ''), k0 = sc.kwAt != null ? sc.kwAt : t0 + 1.0, kd = Math.max(0.2, 0.055 * kw.length);
        cueTimes.push(k0);
        const pill = $('.kw', card);
        tw(pill, k0 + kd, 0.14, { s: [1, 1.07] }, 'out'); tw(pill, k0 + kd + 0.14, 0.3, { s: [1.07, 1] }, 'back');
        TICK.push(t => { const n = Math.round(clamp((t - k0) / kd) * kw.length); const cur = kw.slice(0, n); if (kwt.textContent !== cur) kwt.textContent = cur; });
        kwt.textContent = kw; fitWidth(pill, 720, 0.45); kwt.textContent = '';
        if (sc.sub) {
          const s = el('div', 'sub', esc(sc.sub)); root.appendChild(s); fitWidth(s, 960, 0.5);
          const st = sc.subAt != null ? sc.subAt : k0 + kd + 0.35;
          tw(s, st, 0.7, { o: [0, 1], c: [0, 100], r: [-3, -3] }, 'inOut');
        }
        const line = el('div', 'line'); root.appendChild(line);
        const icons = (tl.mascot && tl.mascot.icons || []).filter(Boolean).slice(0, 5);
        (icons.length ? icons : ['star']).forEach((ic, i) => {
          const m = el('div', '', mascotSVG(8, ic, true)); line.appendChild(m);
          tw(m, t0 + 0.55 + i * 0.09, 0.4, { o: [0, 1], y: [40, 0], s: [0.6, 1] }, 'back');
          const ph = i * 0.9; TICK.push(t => { m.firstChild.style.transform = `translateY(${(Math.sin(t * 5 + ph) * 5).toFixed(2)}px)`; });
        });
      }
    });

    /* --- mascotte principale (scènes hook + section) --- */
    const M = $('#mascot');
    const mScenes = tl.scenes.map((sc, i) => ({ sc, i })).filter(o => o.sc.type !== 'cta');
    const variants = mScenes.map(({ sc, i }) => {
      const d = el('div', '', mascotSVG(9, sc.icon || (tl.mascot && tl.mascot.icons && tl.mascot.icons[i]) || null, false));
      d.style.position = 'absolute'; d.style.inset = '0'; M.appendChild(d);
      const tin = sc.t0 + (i === 0 ? 0.38 : 0.34);
      tw(d, tin, 0.4, { o: [0, 1], y: [-22, 0], s: [0.7, 1], b: [8, 0] }, 'back');
      tw(d, sc.t1 - 0.13, 0.13, { o: [1, 0], b: [0, 10] }, 'in');
      return d;
    });
    const cues = cueTimes.filter(x => x != null).sort((a, b) => a - b);
    TICK.push(t => {
      let bump = 0;
      for (const c of cues) { const x = (t - c) / 0.3; if (x > 0 && x < 1) bump = Math.max(bump, Math.sin(Math.PI * x)); }
      const bob = Math.sin(t * 2.3) * 3 - bump * 16;
      const blink = ((t + 0.4) % 2.9) < 0.11 ? 0.12 : 1;
      variants.forEach(v => {
        if (v.style.visibility === 'hidden') return;
        v.querySelector('svg').style.transform = `translateY(${bob.toFixed(2)}px)`;
        v.querySelector('.meyes').style.transform = `scaleY(${blink})`;
        v.querySelector('.micon').style.transform = `translate(${(bump * 3).toFixed(2)}px,${(-bump * 7 + Math.sin(t * 2.3 + 1) * 2).toFixed(2)}px)`;
      });
    });

    /* --- sous-titres : mots révélés un par un, mot-repère encadré --- */
    const C = $('#captions');
    const caps = (tl.captions || []).map(g => {
      const d = el('div', 'cap'); C.appendChild(d);
      const ws = g.words.map(w => { const s = el('span', 'w' + (w.hl ? ' hl' : ''), esc(w.w)); d.appendChild(s); return { s, t: w.t, o: -1 }; });
      d.style.visibility = 'hidden';
      let k = 1; const fs = 64; let guard = 30;
      while (d.scrollWidth > 860 && k > 0.5 && guard--) { k -= 0.04; ws.forEach(w => { w.s.style.fontSize = (fs * k).toFixed(1) + 'px'; }); }
      return { d, ws, t0: g.t0, t1: g.t1, on: false };
    });
    TICK.push(t => {
      for (const g of caps) {
        const on = t >= g.t0 && t < g.t1;
        if (on !== g.on) { g.d.style.visibility = on ? 'visible' : 'hidden'; g.on = on; }
        if (!on) continue;
        for (const w of g.ws) {
          const p = clamp((t - w.t) / 0.1); const o = Math.round(p * 100) / 100;
          if (o !== w.o) { w.o = o; w.s.style.opacity = o; w.s.style.filter = o < 1 ? `blur(${((1 - o) * 9).toFixed(1)}px)` : ''; w.s.style.transform = o < 1 ? `translateY(${((1 - o) * 6).toFixed(1)}px)` : ''; }
        }
      }
    });

    /* --- fond vivant : taches qui dérivent lentement --- */
    const blobs = [...document.querySelectorAll('.blob')];
    TICK.push(t => {
      blobs.forEach((b, i) => {
        const x = Math.sin(t * 0.21 + i * 2.1) * 46, y = Math.cos(t * 0.17 + i * 1.3) * 54, s = 1 + Math.sin(t * 0.25 + i) * 0.05;
        b.style.transform = `translate(${x.toFixed(1)}px,${y.toFixed(1)}px) scale(${s.toFixed(3)})`;
      });
    });

    for (const it of ITEMS.values()) for (const k in it.p) it.p[k].sort((a, b) => a.t0 - b.t0);

    /* --- contrôle de mise en page (tout affiché) --- */
    renderAt(DUR + 99);
    document.querySelectorAll('.scene').forEach((s, i) => {
      s.style.visibility = 'visible'; s.style.opacity = 1; s.style.filter = '';
      s.querySelectorAll('.ttl,.tx,.big,.chip,.pill,.stamp,.kw,.sub,.note,.label,.cmd').forEach(e => {
        const r = e.getBoundingClientRect();
        if (r.width && (r.left < 24 || r.right > 1056)) report.warnings.push(`scène ${i + 1} : « ${e.textContent.slice(0, 28)} » déborde (${Math.round(r.left)}–${Math.round(r.right)})`);
        if (r.width && r.bottom > 1262 && !s.classList.contains('cta')) report.warnings.push(`scène ${i + 1} : « ${e.textContent.slice(0, 28)} » descend sous la zone de contenu (${Math.round(r.bottom)})`);
      });
    });
    document.querySelectorAll('.scene').forEach(s => { s.style.visibility = ''; s.style.opacity = ''; });
    for (const it of ITEMS.values()) it.hidden = null;
    renderAt(0);
    report.items = ITEMS.size; report.captions = caps.length; report.scenes = tl.scenes.length;
    return report;
  };

  window.renderAt = function (t) {
    for (const it of ITEMS.values()) apply(it, t);
    for (const f of TICK) f(t);
    return true;
  };
})();
