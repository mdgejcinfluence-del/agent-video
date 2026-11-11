/* Moteur de rendu « motion design » — déterministe.
 *
 * La page ne joue RIEN en temps réel. Python appelle init(timeline) une fois, puis renderAt(t) pour
 * chaque image (t en secondes) et prend une capture. Le même t donne toujours la même image : pas de
 * minuteur, pas de hasard, pas de réseau.
 *
 * Une vidéo suit toujours le même fil : RÉSULTAT (ce qui a été produit, dès la première image)
 * -> 3 ÉTAPES (chacune avec sa preuve : demande écrite, extrait de code, rendu, avant/après, erreur
 * corrigée) -> VÉRIFICATION (ce qui a été contrôlé + une limite utile) -> APPEL À L'ACTION (texte imposé).
 * Les médias affichés viennent d'un dossier de preuve (preuves/<id>/) : le moteur ne dessine aucun faux écran.
 */
(function () {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const rich = s => esc(s).replace(/\*([^*]+)\*/g, '<em>$1</em>');        // *mot* -> italique dans la couleur de la série
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const BOTTOM = 1252;                                                     // sous cette ligne : sous-titres puis interface des applications

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
  const rise = (e, t, d = 0.34, dy = 34) => tw(e, t, d, { o: [0, 1], y: [dy, 0], b: [6, 0] }, 'outExpo');

  const I = {
    check: '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="var(--on-good,#fff)" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    cross: '<svg viewBox="0 0 24 24"><path d="M6.5 6.5l11 11M17.5 6.5l-11 11" fill="none" stroke="#fff" stroke-width="3.6" stroke-linecap="round"/></svg>',
    warn: '<svg viewBox="0 0 24 24"><path d="M12 5.5v8.2M12 18.2v.3" fill="none" stroke="#1A1200" stroke-width="3.8" stroke-linecap="round"/></svg>',
    arrow: '<svg viewBox="0 0 24 24"><path d="M4.5 12h14M13 6.2l5.8 5.8-5.8 5.8" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    pen: '<svg viewBox="0 0 24 24"><path d="M4 20l1.2-4.6L16.4 4.2a2 2 0 0 1 2.8 0l.6.6a2 2 0 0 1 0 2.8L8.6 18.8z" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linejoin="round"/></svg>',
    link: '<svg viewBox="0 0 24 24"><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>',
  };
  const fmtInt = n => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0');
  let TL = null, DUR = 0;

  /* ------------------------------------------------------------------ */
  /* Médias : image fixe ou planche d'images (un vrai rendu, lu image par image) */
  /* ------------------------------------------------------------------ */
  function paint(screen, m, sw, sh, o) {
    // dessin dans un canevas : l'image est dans la page au moment de la capture (aucun décodage différé)
    if (!m || !m.imgs || !m.imgs.length) { screen.classList.add('vide'); return; }
    const cv = el('canvas'); cv.width = sw; cv.height = sh; screen.appendChild(cv);
    const ctx = cv.getContext('2d'); ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
    const draw = i => { const im = m.imgs[i]; if (im) ctx.drawImage(im, 0, 0, sw, sh); };
    if (m.imgs.length === 1) { draw(0); return; }
    const start = o.start || 0, off = o.depart != null ? o.depart : (m.depart || 0), loop = o.loop !== false, n = m.imgs.length;
    let last = -1;
    TICK.push(t => {
      let i = Math.floor((Math.max(0, t - start) + off) * m.fps + 1e-6);
      i = loop ? i % n : Math.min(i, n - 1);
      if (i !== last) { last = i; draw(i); }
    });
  }
  function frameBox(ref, cadre, maxW, maxH) {
    const m = TL.media[ref], ar = m ? m.w / m.h : 9 / 16;
    cadre = cadre || (Math.abs(ar - 9 / 16) < 0.03 ? 'telephone' : 'photo');
    const pad = cadre === 'telephone' ? 10 : cadre === 'photo' ? 12 : 0;
    let sw = Math.floor(maxW - 2 * pad), sh = Math.round(sw / ar);
    if (sh > maxH - 2 * pad) { sh = Math.floor(maxH - 2 * pad); sw = Math.round(sh * ar); }
    return { m, cadre, pad, sw, sh, w: sw + 2 * pad, h: sh + 2 * pad };
  }
  function frameEl(ref, cadre, maxW, maxH, o = {}) {
    const b = frameBox(ref, cadre, maxW, maxH);
    const f = el('div', 'frame ' + b.cadre); f.style.width = b.w + 'px'; f.style.height = b.h + 'px';
    const s = el('div', 'screen'); f.appendChild(s); paint(s, b.m, b.sw, b.sh, o);
    if (o.label) { f.appendChild(el('div', 'tagm' + (o.on ? ' on' : ''), esc(o.label))); }
    f._box = b;
    return f;
  }

  /* visuel d'ouverture ou de vérification : un média, ou le contraste avant -> après */
  function visuel(v, zone, W, H, o) {
    if (!v) return [];
    if (v.kind === 'contraste') {
      const bw = Math.floor((W - 74 - 68) / 2), bh = H - 62;
      const dep = (TL.media[v.apres.ref] || {}).depart || 0;
      const a = frameEl(v.avant.ref, v.avant.cadre, bw, bh, { start: o.start, depart: dep, loop: false, label: v.avant.label || 'Avant' });
      const arrow = el('div', 'arrow', I.arrow); arrow.style.color = 'var(--on-accent2)';
      const b = frameEl(v.apres.ref, v.apres.cadre, bw, bh, { start: o.start, depart: dep, loop: false, label: v.apres.label || 'Après', on: true });
      zone.style.alignItems = 'flex-start'; zone.style.paddingTop = Math.max(0, (H - 62 - Math.max(a._box.h, b._box.h)) / 2) + 'px';
      a.style.marginTop = Math.max(0, (b._box.h - a._box.h) / 2) + 'px'; b.style.marginTop = Math.max(0, (a._box.h - b._box.h) / 2) + 'px';
      arrow.style.marginTop = (Math.max(a._box.h, b._box.h) / 2 - 37) + 'px';
      zone.append(a, arrow, b);
      return [a, arrow, b];
    }
    const f = frameEl(v.ref, v.cadre, Math.min(W, o.maxW || 600), H - (v.label ? 62 : 0), { start: o.start, depart: v.depart, loop: false, label: v.label, on: true });
    zone.appendChild(f);
    return [f];
  }

  /* ------------------------------------------------------------------ */
  /* Blocs d'une étape                                                     */
  /* ------------------------------------------------------------------ */
  const MEDIA_KINDS = { media: 1, avant_apres: 1, erreur: 1 };

  function buildMedia(b, wrap, W, H) {
    const at = b.at;
    wrap.style.display = 'flex'; wrap.style.justifyContent = 'center'; wrap.style.alignItems = 'flex-start'; wrap.style.gap = '34px'; wrap.style.height = H + 'px';
    if (b.kind === 'media') {
      const f = frameEl(b.ref, b.cadre, Math.min(W, 620), H - (b.label ? 62 : 0), { start: at, depart: b.depart != null ? b.depart : 0, loop: b.loop, label: b.label, on: true });
      wrap.appendChild(f); tw(f, at, 0.5, { o: [0, 1], s: [0.9, 1], y: [40, 0], r: [-3, 0], b: [8, 0] }, 'back');
    } else if (b.kind === 'avant_apres') {
      const A = TL.media[b.avant.ref], B = TL.media[b.apres.ref];
      const same = A && B && Math.abs(A.w / A.h - B.w / B.h) < 0.03;
      const wt = b.wipeAt != null ? b.wipeAt : at + 0.9, dep = (B || {}).depart || 0;      // les deux rendus avancent ensemble
      if (same) {
        const f = frameEl(b.avant.ref, b.cadre, Math.min(W, 620), H, { start: at, depart: dep, loop: false });
        f.classList.add('aa');
        const s2 = el('div', 'screen apres'); f.appendChild(s2); paint(s2, B, f._box.sw, f._box.sh, { start: at, depart: dep, loop: false });
        const bar = el('div', 'bar'); f.appendChild(bar);
        const av = el('div', 'etq av', esc(b.avant.label || 'Avant')), ap = el('div', 'etq ap', esc(b.apres.label || 'Après')); f.append(av, ap);
        wrap.appendChild(f); tw(f, at, 0.5, { o: [0, 1], s: [0.9, 1], y: [40, 0], b: [8, 0] }, 'back');
        pop(av, at + 0.2, 0.3); pop(ap, wt + 0.5, 0.3);
        const pad = f._box.pad, sw = f._box.sw;
        TICK.push(t => {
          const x = E.inOut(clamp((t - wt) / 0.95));
          s2.style.clipPath = `inset(0 ${((1 - x) * 100).toFixed(2)}% 0 0)`;
          bar.style.left = (pad + x * sw).toFixed(1) + 'px'; bar.style.opacity = (x <= 0 || x >= 1) ? 0 : 1;
        });
      } else {
        const bw = Math.floor((W - 74 - 68) / 2);
        const a = frameEl(b.avant.ref, b.avant.cadre, bw, H - 62, { start: at, depart: dep, loop: false, label: b.avant.label || 'Avant' });
        const arrow = el('div', 'arrow', I.arrow); arrow.style.color = 'var(--on-accent2)';
        const c = frameEl(b.apres.ref, b.apres.cadre, bw, H - 62, { start: at, depart: dep, loop: false, label: b.apres.label || 'Après', on: true });
        const mh = Math.max(a._box.h, c._box.h);
        a.style.marginTop = (mh - a._box.h) / 2 + 'px'; c.style.marginTop = (mh - c._box.h) / 2 + 'px'; arrow.style.marginTop = (mh / 2 - 37) + 'px';
        wrap.append(a, arrow, c);
        tw(a, at, 0.45, { o: [0, 1], s: [0.9, 1], y: [30, 0], b: [8, 0] }, 'back'); pop(arrow, wt - 0.12, 0.3);
        tw(c, wt, 0.5, { o: [0, 1], s: [0.86, 1], x: [-60, 0], b: [10, 0] }, 'back');
      }
    } else if (b.kind === 'erreur') {
      const f = frameEl(b.ref, b.cadre, Math.min(W, 620), H, { start: at });
      f.classList.add('err'); wrap.appendChild(f); tw(f, at, 0.5, { o: [0, 1], s: [0.9, 1], y: [40, 0], b: [8, 0] }, 'back');
      const bx = f._box, z = b.zone || { x: 10, y: 40, w: 80, h: 20 };
      const zx = bx.pad + bx.sw * z.x / 100, zy = bx.pad + bx.sh * z.y / 100, zw = bx.sw * z.w / 100, zh = bx.sh * z.h / 100;
      const zt = b.zoneAt != null ? b.zoneAt : at + 0.7, ft = b.fixAt != null ? b.fixAt : zt + 1.4;
      const mk = (cls, txt, ic) => {
        const ring = el('div', 'ring ' + cls);
        Object.assign(ring.style, { left: (zx - 10) + 'px', top: (zy - 10) + 'px', width: (zw + 20) + 'px', height: (zh + 20) + 'px' });
        const d = el('div', 'diag ' + cls, ic + '<span>' + esc(txt) + '</span>');
        d.style.left = clamp(zx + zw / 2, 90, bx.w - 90) + 'px';
        d.style.top = (zy - 84 > 30 ? zy - 84 : zy + zh + 30) + 'px';
        d.style.translate = '-50% 0';                       // centrage indépendant des animations (transform)
        f.append(ring, d);
        return { ring, d };
      };
      const bad = mk('', b.label || 'défaut', I.cross);
      tw(bad.ring, zt, 0.34, { o: [0, 1], s: [1.25, 1] }, 'outExpo'); tw(bad.d, zt + 0.12, 0.34, { o: [0, 1], s: [0.7, 1], y: [10, 0] }, 'back');
      if (b.fix && TL.media[b.fix.ref]) {
        const s2 = el('div', 'screen'); s2.style.zIndex = 1; f.insertBefore(s2, f.children[1]); paint(s2, TL.media[b.fix.ref], bx.sw, bx.sh, { start: ft });
        tw(s2, ft, 0.4, { o: [0, 1] }, 'inOut');
        const ok = mk('ok', b.fix.label || 'corrigé', I.check);
        tw(bad.ring, ft, 0.2, { o: [1, 0] }, 'in'); tw(bad.d, ft, 0.2, { o: [1, 0] }, 'in');
        tw(ok.ring, ft + 0.1, 0.34, { o: [0, 1], s: [1.15, 1] }, 'outExpo'); tw(ok.d, ft + 0.22, 0.34, { o: [0, 1], s: [0.7, 1], y: [10, 0] }, 'back');
      }
    }
  }

  function buildBlock(b, col) {
    const at = b.at;
    if (b.kind === 'brief') {
      const card = el('div', 'card brief'); col.appendChild(card);
      card.appendChild(el('div', 'label', `${I.pen}<span>${esc(b.label || 'Demande écrite')}</span>${b.extrait ? '<span class="tag">extrait</span>' : ''}`));
      const txt = el('div', 'txt'); card.appendChild(txt);
      // surlignages : on repère chaque passage dans le texte, puis on découpe en mots
      // typographie française : pas de retour à la ligne avant « : ; ? ! » ni après un guillemet ouvrant
      const nb = x => String(x || '').replace(/ ([:;?!»])/g, '\u00a0$1').replace(/« /g, '«\u00a0');
      const text = nb(b.text), ranges = [];
      (b.hl || []).forEach((h, k) => { h = nb(h); const i = text.indexOf(h); if (i >= 0 && h) ranges.push([i, i + h.length, k]); });
      ranges.sort((a, c) => a[0] - c[0]);
      let pos = 0; const parts = [];
      for (const [a, c, k] of ranges) { if (a < pos) continue; if (a > pos) parts.push([text.slice(pos, a), -1]); parts.push([text.slice(a, c), k]); pos = c; }
      if (pos < text.length) parts.push([text.slice(pos), -1]);
      const words = [], marks = [];
      for (const [seg, k] of parts) {
        const host = k >= 0 ? el('mark') : txt, mine = [];
        if (k >= 0) { txt.appendChild(host); marks.push([host, k, mine]); }
        seg.split(/([ \t\n]+)/).forEach(w => {
          if (!w) return;
          if (/^[ \t\n]+$/.test(w)) { host.appendChild(document.createTextNode(' ')); return; }
          const s = el('span', 'w', esc(w)); host.appendChild(s); words.push(s); mine.push(s);
        });
      }
      pop(card, at);
      const t0 = at + 0.22, step = Math.min(0.06, (b.dur || 1.6) / Math.max(1, words.length)), tEnd = t0 + step * words.length;
      const state = words.map(() => -1);
      TICK.push(t => {
        for (let i = 0; i < words.length; i++) { const o = Math.round(clamp((t - (t0 + i * step)) / 0.09) * 20) / 20; if (o !== state[i]) { state[i] = o; words[i].style.opacity = o; } }
        for (const [m, k, mine] of marks) {
          const mt = (b.hlAt && b.hlAt[k] != null) ? Math.max(b.hlAt[k], t0 + 0.1) : tEnd + 0.12 + k * 0.22;
          const p = E.out(clamp((t - mt) / 0.4));
          m.style.backgroundSize = (p * 100).toFixed(1) + '% 100%';
          mine.forEach((w, j) => { w.style.color = p * mine.length > j + 0.45 ? 'var(--mark-ink)' : ''; if (p > 0 && w.style.opacity !== '1') w.style.opacity = 1; });
        }
      });
    } else if (b.kind === 'code') {
      const card = el('div', 'card code'); col.appendChild(card);
      card.appendChild(el('div', 'tab', `<i></i><span>${esc(b.file || 'code')}</span><span class="tag">extrait</span>`));
      const body = el('div', 'body'); card.appendChild(body);
      pop(card, at);
      (b.lines || []).forEach((ln, i) => {
        const lt = (b.lineAt && b.lineAt[i] != null) ? b.lineAt[i] : at + 0.25 + i * 0.16;
        const d = el('div', 'ln', `<span class="no">${i + 1}</span><span class="tx">${esc(ln)}</span>`); body.appendChild(d);
        tw(d, lt, 0.26, { o: [0, 1], x: [-16, 0] });
        if (b.hl === i + 1) {
          const h = el('div', 'hlb'); d.insertBefore(h, d.firstChild);
          const ht = b.hlAt != null ? b.hlAt : at + 0.25 + (b.lines.length) * 0.16 + 0.15;
          TICK.push(t => { h.style.transform = `scaleX(${E.out(clamp((t - ht) / 0.4)).toFixed(4)})`; });
        }
      });
    } else if (b.kind === 'checklist' || b.kind === 'compare') {
      const card = el('div', 'card'); col.appendChild(card);
      if (b.label) card.appendChild(el('div', 'label', esc(b.label)));
      pop(card, at);
      (b.rows || []).forEach((row, i) => {
        const r = typeof row === 'string' ? { text: row, ok: true } : row;
        const rt = (b.rowAt && b.rowAt[i] != null) ? b.rowAt[i] : at + 0.25 + i * 0.3;
        const d = el('div', 'row' + (r.hot ? ' hot' : ''), `<span class="ck${r.ok === false ? ' no' : ''}">${r.ok === false ? I.cross : I.check}</span><span class="tx">${rich(r.text)}</span>`);
        card.appendChild(d);
        tw(d, rt, 0.24, { o: [0, 1], x: [-18, 0], b: [5, 0] });
        tw($('.ck', d), rt + 0.1, 0.3, { o: [0, 1], s: [0.2, 1] }, 'back');
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
        TICK.push(t => { const n = b.value * E.out(clamp((t - t0) / d)); const txt = dec ? n.toFixed(dec).replace('.', ',') : fmtInt(n); if (v.textContent !== txt) v.textContent = txt; });
      }
    } else if (b.kind === 'pill') {
      const w = el('div', 'pillwrap'); const p = el('div', 'pill', rich(b.text)); w.appendChild(p); col.appendChild(w); pop(p, at, 0.34);
    } else if (b.kind === 'terminal') {
      const card = el('div', 'card term'); col.appendChild(card);
      card.innerHTML = `<div class="tab">${esc(b.label || 'commande')}</div><div class="cmd">&gt; <span class="ty"></span><span class="caret"></span></div>`;
      pop(card, at);
      const ty = $('.ty', card), caret = $('.caret', card), txt = String(b.text || ''), t0 = at + 0.3, d = Math.min(1.1, 0.045 * txt.length + 0.2);
      TICK.push(t => {
        const cur = txt.slice(0, Math.round(clamp((t - t0) / d) * txt.length)); if (ty.textContent !== cur) ty.textContent = cur;
        caret.style.opacity = (Math.floor(t * 2.5) % 2 === 0 || (t > t0 && t < t0 + d)) ? 1 : 0;
      });
    } else if (b.kind === 'chips') {
      const w = el('div', 'chips'); col.appendChild(w);
      (b.items || []).forEach((c, i) => { const ch = el('div', 'chip', rich(c)); w.appendChild(ch); pop(ch, (b.itemAt && b.itemAt[i] != null) ? b.itemAt[i] : at + i * 0.22, 0.34); });
    } else if (b.kind === 'note') {
      const card = el('div', 'card note', rich(b.text)); col.appendChild(card); pop(card, at);
    } else if (b.kind === 'source') {
      const s = el('div', 'src', `${I.link}<span>${esc(b.text)}</span>`); col.appendChild(s); rise(s, at, 0.3, 14);
    }
  }

  function fitWidth(e, maxW, min = 0.45) {
    if (!e) return 1; let fs = parseFloat(getComputedStyle(e).fontSize), k = 1, guard = 40;
    while (e.scrollWidth > maxW + 0.5 && k > min && guard--) { k -= 0.03; e.style.fontSize = (fs * k).toFixed(1) + 'px'; }
    return k;
  }
  function fitLines(e, lines, min = 0.5) {
    if (!e) return 1; const cs = getComputedStyle(e), fs = parseFloat(cs.fontSize), lh = parseFloat(cs.lineHeight) / fs; let k = 1, guard = 40;
    while ((e.offsetHeight > lines * lh * fs * k * 1.15 + 2 || e.scrollWidth > e.clientWidth + 0.5) && k > min && guard--) { k -= 0.03; e.style.fontSize = (fs * k).toFixed(1) + 'px'; }
    return k;
  }

  /* ------------------------------------------------------------------ */
  window.init = async function (tl) {
    TL = tl; DUR = tl.duration; TL.media = tl.media || {};
    const th = tl.theme || {}, rs = document.documentElement.style;
    for (const k in th) rs.setProperty('--' + k, th[k]);
    await Promise.all(['800 60px "Inter Tight"', '900 60px "Inter Tight"', '700 60px "Inter Tight"', '600 60px "Inter Tight"', 'italic 60px "Instrument Serif"', '400 20px "JetBrains Mono"', '700 20px "JetBrains Mono"', '700 60px "Caveat"'].map(f => document.fonts.load(f)));
    await document.fonts.ready;
    // les images des preuves doivent être décodées avant la première capture
    const miss = [];
    const load = src => new Promise(res => { const im = new Image(); im.onload = () => (im.decode ? im.decode().then(() => res(im), () => res(im)) : res(im)); im.onerror = () => res(null); im.src = src; });
    await Promise.all(Object.entries(TL.media).map(async ([k, m]) => {
      m.imgs = (await Promise.all((m.srcs || []).map(load))).filter(Boolean);
      if (m.imgs.length !== (m.srcs || []).length || !m.imgs.length) miss.push(k);
    }));
    const report = { warnings: miss.map(k => `média « ${k} » : image illisible, le cadre déborde du contrôle (fichier manquant)`) };
    const scenesRoot = $('#scenes');

    /* repères permanents */
    const hud = $('#hud');
    if (tl.serie) { const s = el('div', 'serie', `<i></i><span>${esc(tl.serie)}</span>`); hud.appendChild(s); }
    else hud.appendChild(el('div'));
    if (tl.fictif) hud.appendChild(el('div', 'fictif', esc(tl.fictif)));

    const steps = tl.scenes.filter(s => s.type === 'etape').length || 3;
    tl.scenes.forEach((sc, idx) => {
      const first = idx === 0, last = idx === tl.scenes.length - 1, t0 = sc.t0, t1 = sc.t1;
      const root = el('div', 'scene ' + sc.type); scenesRoot.appendChild(root);
      if (!first) tw(root, t0, 0.3, { o: [0, 1], y: [46, 0], b: [10, 0] }, 'outExpo');
      if (!last) tw(root, t1 - 0.13, 0.13, { o: [1, 0], y: [0, -28], b: [0, 8] }, 'in');

      const rail = (done, cur) => {
        const r = el('div', 'rail'); root.appendChild(r);
        for (let i = 0; i < steps; i++) {
          const u = el('u'); const b = el('b'); b.appendChild(u); r.appendChild(b);
          if (i < done) u.style.width = '100%';
          else if (i === cur) TICK.push(t => { u.style.width = (clamp((t - t0) / Math.max(0.2, t1 - t0 - 0.2)) * 100).toFixed(1) + '%'; });
        }
      };

      if (sc.type === 'resultat') {
        const head = el('div', 'head', `<div class="ttl">${rich(sc.title)}</div>`); root.appendChild(head);
        const ttl = $('.ttl', head); fitLines(ttl, 2, 0.55);
        if (!first) rise(ttl, t0 + 0.05, 0.4, 40);
        let pub = null;
        if (sc.public) {
          const w = el('div', '', `<div class="public">${I.arrow}<span>${esc(sc.public)}</span></div>`); head.appendChild(w); pub = $('.public', w);
          fitWidth(pub, 940, 0.6);
          tw(pub, sc.publicAt != null ? sc.publicAt : t0 + 1.8, 0.4, { o: [0, 1], s: [0.7, 1], x: [-30, 0], b: [6, 0] }, 'back');
        }
        const top = head.offsetTop + head.offsetHeight + 34, H = BOTTOM - top;
        const zone = el('div', 'zone'); zone.style.top = top + 'px'; zone.style.height = H + 'px'; root.appendChild(zone);
        const els = visuel(sc.visuel, zone, 952, H, { start: t0, maxW: 600 });
        // le résultat est à l'image dès la première image : il se pose, il n'apparaît pas
        els.forEach((e, i) => {
          if (e.classList.contains('arrow')) pop(e, t0 + 0.34, 0.3);
          else if (first && i === 0) tw(e, 0, 0.6, { s: [1.07, 1], r: [-3, 0] }, 'outExpo');
          else if (first) tw(e, 0, 0.7, { s: [0.9, 1], x: [-46, 0], r: [4, 0] }, 'back');
          else tw(e, t0 + 0.1 + i * 0.1, 0.5, { o: [0, 1], s: [0.9, 1], y: [40, 0], b: [8, 0] }, 'back');
        });
      }

      else if (sc.type === 'etape') {
        rail(sc.n - 1, sc.n - 1);
        const head = el('div', 'head', `<div class="kick">Étape <span>${esc(sc.n)}</span>/${steps}</div><div class="ttl">${rich(sc.title)}</div>`); root.appendChild(head);
        fitLines($('.ttl', head), 2, 0.6);
        rise($('.ttl', head), t0 + 0.06, 0.4, 30);
        const top = head.offsetTop + head.offsetHeight + 34;
        const col = el('div', 'col'); col.style.top = top + 'px'; root.appendChild(col);
        const later = [];
        (sc.blocks || []).forEach(b => {
          if (MEDIA_KINDS[b.kind]) { const w = el('div', 'mwrap'); col.appendChild(w); later.push([b, w]); }
          else buildBlock(b, col);
        });
        col.querySelectorAll('.row .tx').forEach(e => fitWidth(e, e.clientWidth, 0.55));
        col.querySelectorAll('.stat .big').forEach(e => fitWidth(e, 880, 0.4));
        col.querySelectorAll('.code').forEach(c => {            // toutes les lignes d'un extrait gardent la même taille
          const max = 952 - 56 - 60; let w = 0; c.querySelectorAll('.ln .tx').forEach(e => { w = Math.max(w, e.scrollWidth); });
          const solo = (sc.blocks || []).length === 1;
          const fs = Math.max(20, Math.min(solo ? 50 : 38, 38 * max / w));
          if (fs !== 38) c.querySelectorAll('.ln').forEach(e => { e.style.fontSize = fs.toFixed(1) + 'px'; e.style.height = Math.round(fs * 1.63) + 'px'; });
        });
        const terms = (sc.blocks || []).filter(b => b.kind === 'terminal');
        col.querySelectorAll('.term .cmd').forEach((e, i) => { const ty = $('.ty', e), full = terms[i]; if (full) { ty.textContent = full.text; fitWidth(e, e.clientWidth, 0.5); ty.textContent = ''; } });
        col.querySelectorAll('.pill, .chip, .src').forEach(e => fitWidth(e, 930, 0.5));
        if (later.length) {
          const free = BOTTOM - top - col.scrollHeight;
          const each = Math.max(260, Math.floor(free / later.length));
          later.forEach(([b, w]) => buildMedia(b, w, 952, each));
        }
        const avail = BOTTOM - top;
        if (!later.length) {
          // une étape sans rendu : le texte prend la place disponible (plus lisible sur un téléphone), puis se pose un peu au-dessus du centre
          const txt = col.querySelector('.brief .txt');
          if (txt && (sc.blocks || []).length === 1) for (const fs of [66, 60, 54]) { txt.style.fontSize = fs + 'px'; if (col.scrollHeight <= avail * 0.62) break; txt.style.fontSize = ''; }
          const free = avail - col.scrollHeight;
          if (free > 40) col.style.top = (top + Math.min(150, free * 0.3)) + 'px';
        }
        if (col.scrollHeight > avail + 1) { const s = avail / col.scrollHeight; col.style.zoom = s.toFixed(3); report.warnings.push(`scène ${idx + 1} : contenu réduit à ${(s * 100).toFixed(0)} %`); }
      }

      else if (sc.type === 'verif') {
        rail(steps, -1);
        const head = el('div', 'head', `<div class="kick"><span>✓</span> Vérification</div><div class="ttl">${rich(sc.title)}</div>`); root.appendChild(head);
        fitLines($('.ttl', head), 2, 0.6); rise($('.ttl', head), t0 + 0.06, 0.4, 30);
        const top = head.offsetTop + head.offsetHeight + 36, H = BOTTOM - top;
        let x0 = 64, W = 952;
        if (sc.visuel) {
          const side = el('div', 'side'); side.style.top = top + 'px'; root.appendChild(side);
          const f = frameEl(sc.visuel.ref, sc.visuel.cadre, 380, Math.min(H, 700), { start: t0, depart: sc.visuel.depart, loop: false });
          side.appendChild(f); tw(f, t0 + 0.1, 0.5, { o: [0, 1], s: [0.88, 1], x: [-40, 0], r: [-4, 0], b: [8, 0] }, 'back');
          x0 = 64 + f._box.w + 32; W = 1016 - x0;
        }
        const rows = el('div', 'rows'); rows.style.left = x0 + 'px'; rows.style.width = W + 'px'; rows.style.top = top + 'px'; root.appendChild(rows);
        (sc.rows || []).forEach((r, i) => {
          const d = el('div', 'vrow', `<span class="ck${r.ok === false ? ' no' : ''}">${r.ok === false ? I.cross : I.check}</span><span class="tx">${rich(r.text)}</span>`); rows.appendChild(d);
          const rt = (sc.rowAt && sc.rowAt[i] != null) ? sc.rowAt[i] : t0 + 0.5 + i * 0.5;
          tw(d, rt, 0.3, { o: [0, 1], x: [30, 0], b: [6, 0] }, 'outExpo'); tw($('.ck', d), rt + 0.12, 0.3, { o: [0, 1], s: [0.2, 1] }, 'back');
        });
        if (sc.limite) {
          const d = el('div', 'vrow lim', `<span class="ck warn">${I.warn}</span><span class="tx"><span class="k">À savoir</span>${rich(sc.limite)}</span>`); rows.appendChild(d);
          const lt = sc.limiteAt != null ? sc.limiteAt : t1 - 1.6;
          tw(d, lt, 0.36, { o: [0, 1], s: [0.92, 1], y: [20, 0], b: [6, 0] }, 'back');
        }
        if (sc.source) { const s = el('div', 'src', `${I.link}<span>${esc(sc.source)}</span>`); s.style.alignSelf = 'flex-start'; rows.appendChild(s); fitWidth(s, W, 0.55); rise(s, sc.sourceAt != null ? sc.sourceAt : t1 - 1.2, 0.3, 14); }
        if (rows.scrollHeight > H + 1) { const s = H / rows.scrollHeight; rows.style.zoom = s.toFixed(3); report.warnings.push(`scène ${idx + 1} : vérification réduite à ${(s * 100).toFixed(0)} %`); }
      }

      else if (sc.type === 'cta') {
        if (tl.avatar) { const a = el('div', 'avatar'); a.style.backgroundImage = `url("${tl.avatar}")`; root.appendChild(a); pop(a, t0 + 0.12, 0.45); }
        const card = el('div', 'ctacard', `<div class="cta-word">${esc(sc.verb || 'Commente')}</div><div class="kw"><span class="kwt"></span><span class="caret"></span></div><div class="l2">${esc(sc.l2 || '')}</div>`);
        root.appendChild(card);
        tw(card, t0 + 0.04, 0.5, { o: [0, 1], y: [80, 0], r: [-8, -2], b: [10, 0], s: [0.9, 1] }, 'back');
        const kwt = $('.kwt', card), kw = String(sc.keyword || ''), k0 = sc.kwAt != null ? sc.kwAt : t0 + 0.6, kd = Math.max(0.2, 0.055 * kw.length);
        const pill = $('.kw', card);
        tw(pill, k0 + kd, 0.14, { s: [1, 1.07] }, 'out'); tw(pill, k0 + kd + 0.14, 0.3, { s: [1.07, 1] }, 'back');
        // tant que le mot-clé n'est pas prononcé, un curseur clignote dans la pastille (elle n'a jamais l'air vide)
        const caret = $('.caret', card);
        TICK.push(t => {
          const cur = kw.slice(0, Math.round(clamp((t - k0) / kd) * kw.length)); if (kwt.textContent !== cur) kwt.textContent = cur;
          const typing = t < k0 + kd, lit = t >= k0 || Math.floor(Math.max(0, t - t0) / 0.4) % 2 === 0;
          caret.style.display = typing ? '' : 'none'; caret.style.opacity = typing && lit ? '1' : '0';
        });
        kwt.textContent = kw; caret.style.display = 'none'; fitWidth(pill, 740, 0.45); kwt.textContent = ''; caret.style.display = '';
        const l2 = $('.l2', card); fitWidth(l2, 780, 0.6);
        tw(l2, sc.l2At != null ? sc.l2At : k0 + kd + 0.2, 0.34, { o: [0, 1], y: [18, 0], b: [5, 0] }, 'outExpo');
        if (sc.l3) {
          // la phrase imposée s'affiche en entier, coupée seulement à la virgule
          const parts = String(sc.l3).split(/,\s+/); const html = parts.map((p, i) => `<span>${esc(p + (i < parts.length - 1 ? ',' : ''))}</span>`).join('');
          const s = el('div', 'l3', html); root.appendChild(s);
          s.querySelectorAll('span').forEach(e => fitWidth(e, 940, 0.55));
          const st = sc.subAt != null ? sc.subAt : k0 + kd + 0.9;
          s.querySelectorAll('span').forEach((e, i) => tw(e, st + i * 0.55, 0.6, { o: [0, 1], c: [0, 100] }, 'inOut'));
        }
      }
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

    /* --- fond vivant : halos qui dérivent lentement --- */
    const blobs = [...document.querySelectorAll('.blob')];
    TICK.push(t => {
      blobs.forEach((b, i) => {
        const x = Math.sin(t * 0.21 + i * 2.1) * 46, y = Math.cos(t * 0.17 + i * 1.3) * 54, s = 1 + Math.sin(t * 0.25 + i) * 0.05;
        b.style.transform = `translate(${x.toFixed(1)}px,${y.toFixed(1)}px) scale(${s.toFixed(3)})`;
      });
    });

    for (const it of ITEMS.values()) for (const k in it.p) it.p[k].sort((a, b) => a.t0 - b.t0);

    /* --- contrôle de mise en page (tout affiché, état final de chaque scène) --- */
    renderAt(DUR + 99);
    document.querySelectorAll('.scene').forEach((s, i) => {
      s.style.visibility = 'visible'; s.style.opacity = 1; s.style.filter = ''; s.style.transform = '';
      s.querySelectorAll('.ttl,.public,.tx,.big,.chip,.pill,.kw,.l2,.l3 span,.note,.label,.cmd,.frame,.vrow,.card,.tagm,.src').forEach(e => {
        const r = e.getBoundingClientRect();
        if (r.width && (r.left < 24 || r.right > 1056)) report.warnings.push(`scène ${i + 1} : « ${(e.textContent || e.className).slice(0, 28)} » déborde (${Math.round(r.left)}–${Math.round(r.right)})`);
        if (r.width && r.bottom > BOTTOM + 10 && !s.classList.contains('cta')) report.warnings.push(`scène ${i + 1} : « ${(e.textContent || e.className).slice(0, 28)} » descend sous la zone de contenu (${Math.round(r.bottom)})`);
      });
    });
    document.querySelectorAll('.scene').forEach(s => { s.style.visibility = ''; s.style.opacity = ''; });
    for (const it of ITEMS.values()) it.hidden = null;
    renderAt(0);
    report.items = ITEMS.size; report.captions = caps.length; report.scenes = tl.scenes.length; report.media = Object.keys(TL.media).length;
    return report;
  };

  window.renderAt = function (t) {
    for (const it of ITEMS.values()) apply(it, t);
    for (const f of TICK) f(t);
    return true;
  };
})();
