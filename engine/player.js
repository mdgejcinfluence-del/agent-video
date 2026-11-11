/* Moteur de rendu « format mascotte » — déterministe.
 *
 * La page ne joue RIEN en temps réel. Python appelle init(timeline) une fois, puis renderAt(t) pour
 * chaque image (t en secondes) et prend une capture. Le même t donne toujours la même image : pas de
 * minuteur, pas de hasard, pas de réseau. renderAt(-1) affiche la couverture (miniature).
 *
 * Grammaire d'une vidéo : une suite d'ÉCRANS (titre en majuscules, tuile numérotée facultative,
 * un ou deux blocs, le personnage dans une pose) puis l'écran de FIN (abonne-toi + mot à commenter).
 * Les sous-titres sont en haut : trois mots au plus, le mot prononcé est surligné.
 * Un bloc « rush » ou « avant_apres » affiche une vraie séquence filmée (banque libre de droits),
 * lue image par image dans un canevas ; le montage (titre, sous-titres, zoom, couleurs, barre) est
 * réellement appliqué par ce moteur.
 */
(function () {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  // typographie : pas de retour à la ligne avant « : ; ? ! », ni au milieu d'un nombre, ni entre un nombre et ce qu'il compte
  const nb = x => String(x == null ? '' : x)
    .replace(/ ([:;?!»])/g, '\u00a0$1').replace(/« /g, '«\u00a0')
    .replace(/(\d) (?=\d{3}(?!\d))/g, '$1\u00a0')
    .replace(/(\d) (?=[A-Za-zÀ-ÿ%€$])/g, '$1\u00a0');
  // *mot* -> surligné ; « / » entouré d'espaces -> retour à la ligne voulu
  const rich = s => esc(nb(s)).replace(/\*([^*]+)\*/g, '<em>$1</em>').replace(/\s+\/\s+/g, '<br>');
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const X0 = 60, W = 960, TOP = 292, FEET = 1752, TEXT_MAX = 1500;

  const E = {
    lin: x => x,
    out: x => 1 - Math.pow(1 - x, 3),
    outExpo: x => (x >= 1 ? 1 : 1 - Math.pow(2, -10 * x)),
    inOut: x => (x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2),
    back: x => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); },
    in: x => x * x * x,
  };

  /* ---------------- interpolations : par élément et par propriété, une liste d'étapes ---------------- */
  const ITEMS = new Map();
  const TICK = [];        // fonctions synchrones appelées à chaque image
  const ASYNC = [];       // fonctions qui peuvent attendre le décodage d'une image de rush
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
    if (p.c) { const c = val(p.c, t); s.clipPath = c >= 99.9 ? '' : `inset(0 ${(100 - c).toFixed(2)}% 0 0)`; }
  }
  const pop = (e, t, d = 0.32) => { if (t > 0.001) tw(e, t, d, { o: [0, 1], s: [0.72, 1] }, 'back'); };      // t = 0 : déjà là à la première image
  const rise = (e, t, d = 0.34, dy = 44) => tw(e, t, d, { o: [0, 1], y: [dy, 0] }, 'outExpo');
  const slide = (e, t, d = 0.3, dx = -60) => tw(e, t, d, { o: [0, 1], x: [dx, 0] }, 'outExpo');
  const bump = (e, t, k = 1.08) => { tw(e, t, 0.1, { s: [1, k] }, 'out'); tw(e, t + 0.1, 0.22, { s: [k, 1] }, 'back'); };

  /* ---------------- pictogrammes (traits bleu nuit, une touche de jaune) ---------------- */
  const S = 'fill="none" stroke="#0E1A38" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"';
  const Y = 'fill="#FFC531" stroke="#0E1A38" stroke-width="3.4" stroke-linejoin="round"';
  const svg = b => `<svg viewBox="0 0 48 48">${b}</svg>`;
  const ICON = {
    video: svg(`<rect x="5" y="13" width="26" height="22" rx="3" ${Y}/><path d="M31 21l11-6v18l-11-6z" ${S}/>`),
    voix: svg(`<rect x="18" y="5" width="12" height="22" rx="6" ${Y}/><path d="M11 23a13 13 0 0 0 26 0M24 36v7M17 43h14" ${S}/>`),
    image: svg(`<rect x="5" y="8" width="38" height="32" rx="3" ${S}/><circle cx="16" cy="18" r="4" ${Y}/><path d="M7 36l11-11 8 8 6-6 10 9" ${S}/>`),
    texte: svg(`<path d="M9 12V8h30v4M24 8v32M17 40h14" ${S}/>`),
    lien: svg(`<path d="M20 28a8 8 0 0 0 11.3 0l6-6A8 8 0 0 0 26 10.700l-2.5 2.5M28 20a8 8 0 0 0-11.3 0l-6 6A8 8 0 0 0 22 37.300l2.5-2.5" ${S}/>`),
    telephone: svg(`<rect x="13" y="4" width="22" height="40" rx="4" ${Y}/><path d="M21 38h6" ${S}/>`),
    ordi: svg(`<rect x="8" y="9" width="32" height="22" rx="2" ${Y}/><path d="M3 38h42M18 31v7M30 31v7" ${S}/>`),
    horloge: svg(`<circle cx="24" cy="26" r="16" ${Y}/><path d="M24 17v9l6 4M19 5h10" ${S}/>`),
    cadenas: svg(`<rect x="9" y="21" width="30" height="22" rx="3" ${Y}/><path d="M15 21v-6a9 9 0 0 1 18 0v6M24 30v5" ${S}/>`),
    loupe: svg(`<circle cx="21" cy="21" r="13" ${Y}/><path d="M31 31l11 11" ${S}/>`),
    argent: svg(`<circle cx="24" cy="24" r="18" ${Y}/><path d="M29 17c-1.500-2-4-3-6-3-3.500 0-6 2-6 5 0 6.500 13 3.500 13 10 0 3-2.500 5-6.500 5-2.500 0-5-1-6.500-3M24 10v4M24 34v4" ${S}/>`),
    message: svg(`<path d="M6 9h36v24H22l-10 8v-8H6z" ${Y}/><path d="M15 18h18M15 25h11" ${S}/>`),
    coche: svg(`<circle cx="24" cy="24" r="18" ${Y}/><path d="M15 25l6 6 12-13" ${S}/>`),
    croix: svg(`<circle cx="24" cy="24" r="18" ${S}/><path d="M17 17l14 14M31 17L17 31" ${S}/>`),
    etoile: svg(`<path d="M24 5l5.800 12 13.200 1.800-9.600 9.200 2.400 13L24 34.800 12.200 41l2.400-13L5 18.800 18.200 17z" ${Y}/>`),
    panier: svg(`<path d="M4 8h7l5 22h21l4-15H13" ${S}/><circle cx="19" cy="38" r="3.500" ${Y}/><circle cx="34" cy="38" r="3.500" ${Y}/>`),
    photo: svg(`<path d="M5 14h9l3-5h14l3 5h9v25H5z" ${Y}/><circle cx="24" cy="26" r="7.500" ${S}/>`),
    musique: svg(`<path d="M18 36V10l22-4v26" ${S}/><circle cx="12" cy="36" r="6" ${Y}/><circle cx="34" cy="32" r="6" ${Y}/>`),
    robot: svg(`<rect x="8" y="15" width="32" height="24" rx="5" ${Y}/><path d="M24 15V7M19 39v4M29 39v4M3 25v8M45 25v8" ${S}/><circle cx="17.500" cy="26" r="2.600" fill="#0E1A38"/><circle cx="30.500" cy="26" r="2.600" fill="#0E1A38"/><path d="M19 33h10" ${S}/>`),
    ciseaux: svg(`<circle cx="11" cy="13" r="6" ${Y}/><circle cx="11" cy="35" r="6" ${Y}/><path d="M16 16l27 20M16 32L43 12" ${S}/>`),
    idee: svg(`<path d="M24 5a13 13 0 0 0-7.500 23.600V34h15v-5.400A13 13 0 0 0 24 5z" ${Y}/><path d="M18 40h12M21 45h6" ${S}/>`),
    cible: svg(`<circle cx="24" cy="24" r="18" ${S}/><circle cx="24" cy="24" r="10" ${Y}/><circle cx="24" cy="24" r="2.500" fill="#0E1A38"/>`),
    fleche: svg(`<path d="M6 24h34M27 11l13 13-13 13" ${S}/>`),
    dossier: svg(`<path d="M4 11h15l4 5h21v24H4z" ${Y}/>`),
    oeil: svg(`<path d="M3 24s8-13 21-13 21 13 21 13-8 13-21 13S3 24 3 24z" ${Y}/><circle cx="24" cy="24" r="6" ${S}/>`),
  };
  const CHECK = '<svg viewBox="0 0 24 24"><path d="M4.500 12.500l5 5L19.500 7" fill="none" stroke="#0E1A38" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const TIMER = `<svg viewBox="0 0 48 48"><circle cx="24" cy="27" r="16" fill="#fff" stroke="#0E1A38" stroke-width="3.6"/><path d="M24 27V11a16 16 0 0 1 13.900 8z" fill="#FFC531" stroke="#0E1A38" stroke-width="3" stroke-linejoin="round"/><path d="M19 5h10M24 5v6" fill="none" stroke="#0E1A38" stroke-width="3.6" stroke-linecap="round"/></svg>`;
  const CURSOR = '<svg viewBox="0 0 32 32"><path d="M6 3l19 15-9 1.500 5 9-4.500 2.500-5-9.500L6 27z" fill="#fff" stroke="#0E1A38" stroke-width="2.400" stroke-linejoin="round"/></svg>';

  let TL = null, DUR = 0;
  const report = { warnings: [] };

  /* ---------------- ajustement du texte ---------------- */
  const RANGE = document.createRange();
  const contentW = e => { RANGE.selectNodeContents(e); return RANGE.getBoundingClientRect().width; };   // largeur réelle du contenu, quel que soit l'affichage
  function fitW(e, maxW, min = 0.5) {            // une seule ligne : on réduit le corps jusqu'à ce que le contenu tienne dans maxW
    if (!e) return 1; const fs = parseFloat(getComputedStyle(e).fontSize); let k = 1, guard = 40;
    while (contentW(e) > maxW + 0.5 && k > min && guard--) { k -= 0.03; e.style.fontSize = (fs * k).toFixed(1) + 'px'; }
    return k;
  }
  function fitBox(e, maxW, maxH, min = 0.45) {   // plusieurs lignes : on réduit jusqu'à tenir dans la boîte
    if (!e) return 1; const fs = parseFloat(getComputedStyle(e).fontSize); let k = 1, guard = 44;
    while ((e.scrollHeight > maxH + 1 || e.scrollWidth > maxW + 1) && k > min && guard--) { k -= 0.03; e.style.fontSize = (fs * k).toFixed(1) + 'px'; }
    return k;
  }

  /* ---------------- personnage ---------------- */
  function masc(pose) {
    const av = TL.avatar || {}, poses = av.poses || {};
    const name = poses[pose] ? pose : (poses.presente ? 'presente' : Object.keys(poses)[0]);
    if (!name) return null;
    const im = el('img', 'masc'); im.src = av.base + name + '.png'; im._p = poses[name]; im._name = name;
    return im;
  }
  function placeMasc(im, k, cx) {               // k : échelle (1 = un personnage debout de 1000 px) ; cx : centre horizontal
    const p = im._p, w = p.w * k, h = p.h * k;
    im.style.width = w.toFixed(1) + 'px'; im.style.height = h.toFixed(1) + 'px';
    im.style.left = (cx - w / 2).toFixed(1) + 'px'; im.style.top = (FEET - (p.h - p.pieds) * k).toFixed(1) + 'px';
    return { w, h, top: FEET - (p.h - p.pieds) * k };
  }

  /* ---------------- rushs : images décodées à la demande ---------------- */
  const CACHE = new Map();
  function frameImg(m, i) {
    const src = m.dir + String(i + 1).padStart(4, '0') + '.' + (m.ext || 'jpg');
    let p = CACHE.get(src);
    if (!p) {
      p = new Promise(res => { const im = new Image(); im.onload = () => (im.decode ? im.decode().then(() => res(im), () => res(im)) : res(im)); im.onerror = () => res(null); im.src = src; });
      CACHE.set(src, p);
      if (CACHE.size > 48) CACHE.delete(CACHE.keys().next().value);
    }
    return p;
  }
  function sequence(cvs, ref, o) {              // dessine la séquence dans un ou plusieurs canevas, à partir de o.start
    const m = TL.media[ref]; if (!m || !m.n) return false;
    const ctxs = cvs.map(c => c.getContext('2d')); let last = -1;
    ASYNC.push(async t => {
      if (t < o.t0 - 0.05 || t > o.t1 + 0.05) return;
      let i = Math.floor(Math.max(0, t - o.start) * m.fps + 1e-6);
      i = Math.min(i, m.n - 1);                  // séquence préparée à la bonne durée : on tient la dernière image, jamais de saut
      if (i === last) return;
      const im = await frameImg(m, i);
      if (im) { ctxs.forEach((c, k) => c.drawImage(im, 0, 0, cvs[k].width, cvs[k].height)); last = i; }
    });
    return true;
  }
  const CADRE = { paysage: [888, 500], portrait: [396, 704], carre: [586, 586] };
  function rushFrame(b, sc) {
    const m = TL.media[b.ref], cadre = CADRE[b.cadre] ? b.cadre : 'paysage', [w, h] = CADRE[cadre];
    const f = el('div', 'rush ' + cadre); f.style.width = (w + 14) + 'px'; f.style.height = (h + 14) + 'px';
    const cv = el('canvas'); cv.width = w; cv.height = h; cv.style.width = w + 'px'; cv.style.height = h + 'px'; f.appendChild(cv);
    if (!m || !m.n) { f.classList.add('vide'); report.warnings.push(`rush « ${b.ref} » : séquence absente`); }
    return { f, cv, w, h, ok: !!(m && m.n) };
  }

  /* ---------------- blocs ---------------- */
  function buildBlock(b, col, sc) {
    const k = b.kind, t1 = sc.t1; let e, fit = () => {}, anim = () => {};
    if (k === 'liste') {
      e = el('div', 'liste');
      const rows = b.items.map((s, i) => { const r = el('div', 'bar', `<i>${i + (b.debut || 1)}</i><span>${rich(s)}</span>`); e.appendChild(r); return r; });
      fit = () => rows.forEach(r => fitW($('span', r), r.clientWidth - 126));
      anim = () => rows.forEach((r, i) => slide(r, b.itemAt[i]));
    } else if (k === 'check') {
      e = el('div', 'check');
      const rows = b.items.map(s => { const r = el('div', 'row', `<i>${CHECK}</i><span>${rich(s)}</span>`); e.appendChild(r); return r; });
      fit = () => rows.forEach(r => fitW($('span', r), r.clientWidth - 124));
      anim = () => rows.forEach((r, i) => { slide(r, b.itemAt[i]); const c = $('svg', r); tw(c, b.itemAt[i] + 0.16, 0.2, { o: [0, 1], s: [0.3, 1] }, 'back'); });
    } else if (k === 'cartes') {
      e = el('div', 'cartes');
      const cs = b.cards.map(c => {
        const d = el('div', 'carte ' + (c.ton === 'oui' ? 'oui' : 'non'), `<div class="bx"><small>${rich(c.tag)}</small><b>${rich(c.text)}</b></div>` + (c.note ? `<div class="note">${rich(c.note)}</div>` : ''));
        e.appendChild(d); return d;
      });
      fit = () => cs.forEach(d => { const bx = $('.bx', d); fitBox($('b', d), bx.clientWidth - 44, 190); fitBox($('small', d), bx.clientWidth - 44, 80); fitW($('.note', d), d.clientWidth - 84); });
      anim = () => cs.forEach((d, i) => { pop($('.bx', d), b.cardAt[i]); const n = $('.note', d); if (n) pop(n, b.noteAt && b.noteAt[i] != null ? b.noteAt[i] : b.cardAt[i] + 0.5); });
    } else if (k === 'icones') {
      e = el('div', 'icones');
      const it = b.items.map(x => { const d = el('div', 'ico', `${ICON[x.icon] || ICON.idee}<span>${rich(x.label)}</span>`); e.appendChild(d); return d; });
      fit = () => it.forEach(d => fitW($('span', d), d.clientWidth - 36));
      anim = () => it.forEach((d, i) => pop(d, b.itemAt[i]));
    } else if (k === 'chrono') {
      e = el('div', 'chrono', `${TIMER}<div><em>${esc(b.valeur)}</em> ${esc(b.unite)}</div>`);
      fit = () => fitW($('div', e), col.clientWidth - 230);
      anim = () => { pop(e, b.at); tw($('svg', e), b.at, 0.5, { r: [-28, 0] }, 'back'); };
    } else if (k === 'fenetre') {
      e = el('div', 'fen', `<div class="tb"><i></i>${esc(b.titre || 'Assistant IA')}</div><div class="bd"><div class="q"><span></span><u class="caret"></u></div>${b.reponse ? '<div class="r"><span></span></div>' : ''}</div>`);
      const q = $('.q', e), qs = $('.q span', e), r = $('.r', e), rs = r ? $('span', r) : null;
      fit = () => { qs.textContent = b.question; if (rs) rs.textContent = b.reponse; };
      anim = () => {
        pop(e, b.at); tw(q, b.qAt - 0.12, 0.2, { o: [0, 1] }, 'out'); if (r) tw(r, b.rAt, 0.25, { o: [0, 1], y: [18, 0] }, 'outExpo');
        const qd = Math.min(1.1, Math.max(0.4, b.question.length * 0.035)), caret = $('.caret', e);
        TICK.push(t => {
          const n = Math.round(clamp((t - b.qAt) / qd) * b.question.length), cur = b.question.slice(0, n);
          if (qs.textContent !== cur) qs.textContent = cur;
          caret.style.visibility = t < b.qAt + qd + 0.3 && Math.floor(Math.max(0, t - sc.t0) / 0.3) % 2 === 0 ? 'inherit' : 'hidden';
          if (rs) { const rd = Math.min(1.2, Math.max(0.4, b.reponse.length * 0.025)), m2 = Math.round(clamp((t - b.rAt - 0.15) / rd) * b.reponse.length), c2 = b.reponse.slice(0, m2); if (rs.textContent !== c2) rs.textContent = c2; }
        });
      };
    } else if (k === 'prompt') {
      // l'instruction à copier : la fenêtre de l'outil, le texte exact tapé au clavier, les [champs à remplacer] surlignés
      e = el('div', 'fen pr', `<div class="tb"><i></i><span>${esc(b.outil || 'Assistant IA')}</span><small>à copier</small></div><div class="bd"><div class="pt"><span></span><u class="caret"></u></div></div>`);
      const pt = $('.pt', e), ps = $('.pt span', e), txt = String(b.texte || '');
      const segs = txt.split(/(\[[^\[\]]{1,40}\])/).filter(x => x !== '').map(x => ({ x, hot: /^\[[^\[\]]{1,40}\]$/.test(x) }));
      const html = n => { let out = '', left = n; for (const g of segs) { if (left <= 0) break; const part = g.x.slice(0, left); left -= part.length; out += g.hot ? `<mark>${esc(part)}</mark>` : esc(part); } return out; };
      fit = () => {
        ps.innerHTML = html(txt.length);
        const maxH = Math.max(120, Math.min(700, b.maxH || 700));
        fitBox(pt, pt.clientWidth, maxH, 0.62);
        pt.style.height = pt.offsetHeight + 'px';          // la fenêtre garde sa taille finale pendant la frappe
        ps.innerHTML = '';
      };
      anim = () => {
        pop(e, b.at);
        const t0_ = b.typeAt, t1_ = Math.max(b.typeEnd, b.typeAt + 0.3), caret = $('.caret', e); let shown = -1;
        TICK.push(t => {
          const n = Math.round(clamp((t - t0_) / (t1_ - t0_)) * txt.length);
          if (n !== shown) { shown = n; ps.innerHTML = html(n); }
          caret.style.visibility = t < t1_ + 0.4 && Math.floor(Math.max(0, t - sc.t0) / 0.3) % 2 === 0 ? 'inherit' : 'hidden';
        });
      };
    } else if (k === 'reponse') {
      // un extrait d'une vraie réponse : le titre, puis les lignes une à une ; la mention dit d'où vient la réponse
      e = el('div', 'fen rp', `<div class="tb"><i></i><span>Réponse de l'IA</span></div><div class="bd"><div class="rt">${rich(b.titre || 'Réponse')}</div>` +
        (b.lignes || []).map(x => `<div class="rl"><span>${rich(x)}</span></div>`).join('') + (b.source ? `<div class="src">${esc(b.source)}</div>` : '') + '</div>');
      const rows = [...e.querySelectorAll('.rl')], rt = $('.rt', e), src = $('.src', e);
      fit = () => { fitW(rt, e.clientWidth - 76, 0.6); rows.forEach(r => fitW($('span', r), r.clientWidth - 44, 0.6)); if (src) fitW(src, e.clientWidth - 76, 0.6); };
      anim = () => { pop(e, b.at); rows.forEach((r, i) => slide(r, b.lineAt[i], 0.28, -40)); if (src) tw(src, (b.lineAt[b.lineAt.length - 1] || b.at) + 0.35, 0.3, { o: [0, 1] }, 'out'); };
    } else if (k === 'mot') {
      e = el('div', 'mot', `<b>${rich(b.text)}</b>` + (b.sous ? `<span>${rich(b.sous)}</span>` : ''));
      fit = () => { fitW($('b', e), col.clientWidth - 124); };
      anim = () => { pop($('b', e), b.at); const s = $('span', e); if (s) rise(s, b.sousAt != null ? b.sousAt : b.at + 0.4); };
    } else if (k === 'etiquette') {
      e = el('div', 'etq', rich(b.text));
      fit = () => fitW(e, col.clientWidth - 80);
      anim = () => pop(e, b.at);
    } else if (k === 'tuiles_video') {
      e = el('div', 'tv');
      const n = Math.max(2, Math.min(4, b.n || 4)), vs = [];
      for (let i = 0; i < n; i++) { const v = el('div', 'v', '<i></i><u><s></s></u>'); e.appendChild(v); vs.push(v); }
      anim = () => { vs.forEach((v, i) => pop(v, b.at + i * 0.16)); TICK.push(t => vs.forEach((v, i) => { $('s', v).style.width = (clamp((t - b.at - i * 0.16) / Math.max(1, t1 - b.at)) * (62 + 9 * i)).toFixed(1) + '%'; })); };
    } else if (k === 'rush') {
      const fr = rushFrame(b, sc); e = fr.f;
      if (b.label) e.appendChild(el('div', 'tag', esc(b.label)));
      anim = () => { pop(e, b.at); if (fr.ok) sequence([fr.cv], b.ref, { start: b.at, t0: b.at - 0.1, t1: sc.t1 }); };
    } else if (k === 'avant_apres') {
      // un seul cadre : la séquence brute, puis un volet qui révèle la même séquence montée ; chaque effet est réellement appliqué ici
      e = el('div', 'aa');
      const fr = rushFrame(b, sc); e.appendChild(fr.f);
      const fx = el('div', 'fx'); fr.f.appendChild(fx);
      const cv2 = el('canvas'); cv2.width = fr.w; cv2.height = fr.h; cv2.style.width = fr.w + 'px'; cv2.style.height = fr.h + 'px'; fx.appendChild(cv2);
      const sep = el('div', 'sep'); fr.f.appendChild(sep);
      const tagA = el('div', 'tag', 'Avant · rush brut'), tagB = el('div', 'tag on', 'Après · monté'); fr.f.appendChild(tagA); fr.f.appendChild(tagB);
      const eff = (b.effets || []).filter(x => ['couleurs', 'zoom', 'titre', 'sous_titres', 'barre'].includes(x));
      const NOM = { couleurs: 'Couleurs', zoom: 'Zoom', titre: 'Titre', sous_titres: 'Sous-titres', barre: 'Barre' };
      const chips = el('div', 'chips'); e.appendChild(chips);
      const chip = {}; eff.forEach(x => { chip[x] = el('span', '', NOM[x]); chips.appendChild(chip[x]); });
      const at = x => { const i = eff.indexOf(x); return i < 0 ? null : b.fxAt[i]; };
      let ttl = null, cap = null, bar = null, words = [];
      if (at('titre') != null && b.titre) { ttl = el('div', 'fxt', rich(b.titre)); fx.appendChild(ttl); }
      if (at('sous_titres') != null && b.sous_titre) { cap = el('div', 'fxc'); words = String(b.sous_titre).split(/\s+/).slice(0, 4).map(w => { const s = el('span', '', esc(w)); cap.appendChild(s); return s; }); fx.appendChild(cap); }
      if (at('barre') != null) { bar = el('div', 'fxb'); fx.appendChild(bar); }
      fit = () => { if (ttl) fitBox(ttl, fr.w, fr.h * 0.36); if (cap) fitW(cap, fr.w - 30); };
      anim = () => {
        pop(fr.f, b.at); if (fr.ok) sequence([fr.cv, cv2], b.ref, { start: b.at, t0: b.at - 0.1, t1: sc.t1 });
        const w0 = b.wipeAt, wd = 0.55;
        tw(fx, w0, wd, { c: [0, 100] }, 'inOut');
        tw(tagA, b.at + 0.15, 0.2, { o: [0, 1] }, 'out'); tw(tagA, w0 + wd * 0.5, 0.15, { o: [1, 0] }, 'in'); pop(tagB, w0 + wd * 0.6);
        chips.childNodes.forEach(c => tw(c, b.at + 0.2, 0.25, { o: [0, 1] }, 'out'));
        if (ttl) pop(ttl, at('titre')); if (cap) rise(cap, at('sous_titres'), 0.3, 20); 
        const zt = at('zoom'), ct = at('couleurs'), bt = at('barre'), st = at('sous_titres');
        TICK.push(t => {
          const p = clamp((t - w0) / wd), x = (p < .5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2) * (fr.w + 6) - 6;
          sep.style.transform = `translateX(${x.toFixed(1)}px)`; sep.style.visibility = p > 0 && p < 1 ? 'inherit' : 'hidden';
          const z = zt == null ? 1 : 1 + 0.17 * E.inOut(clamp((t - zt) / 1.1));
          cv2.style.transform = z > 1.001 ? `scale(${z.toFixed(4)})` : '';
          const c = ct == null ? 0 : clamp((t - ct) / 0.4);
          cv2.style.filter = c > 0 ? `contrast(${(1 + 0.14 * c).toFixed(3)}) saturate(${(1 + 0.38 * c).toFixed(3)}) brightness(${(1 + 0.04 * c).toFixed(3)})` : '';
          if (bar) bar.style.width = (clamp((t - bt) / Math.max(0.8, t1 - bt - 0.2)) * 100).toFixed(1) + '%';
          if (cap && words.length) { const i = t < st ? -1 : Math.floor((t - st) / 0.34) % words.length; words.forEach((s, j) => { const on = j === i; if (s._on !== on) { s._on = on; s.className = on ? 'on' : ''; } }); }
          eff.forEach((xn, i) => { const on = t >= b.fxAt[i]; if (chip[xn]._on !== on) { chip[xn]._on = on; chip[xn].className = on ? 'on' : ''; } });
        });
        eff.forEach((xn, i) => bump(chip[xn], b.fxAt[i], 1.12));
      };
    } else {
      e = el('div'); report.warnings.push(`bloc inconnu : ${k}`);
    }
    col.appendChild(e);
    return { e, fit, anim, kind: k, b };
  }

  /* ---------------- écran ---------------- */
  function buildEcran(sc, root, idx) {
    const first = idx === 0, t0 = sc.t0;
    let hb;
    if (sc.tuile) {
      const TW_ = 236, TH_ = 252;
      const tile = el('div', 'tuile', `<span>${esc(sc.tuile.label)}</span><b>${esc(sc.tuile.n)}</b>`); root.appendChild(tile);
      tile.style.left = X0 + 'px'; tile.style.top = TOP + 'px'; fitW($('span', tile), 196); fitW($('b', tile), 200);
      const ttl = el('div', 'ttl cote', `<span>${rich(sc.title)}</span>`); root.appendChild(ttl);
      ttl.style.left = (X0 + TW_ + 44) + 'px'; ttl.style.top = TOP + 'px'; ttl.style.width = (W - TW_ - 44) + 'px'; ttl.style.height = (TH_ + 8) + 'px';
      fitBox($('span', ttl), W - TW_ - 44, TH_ + 8);
      const a = sc.tuile.at, mv = Math.max(a + 0.42, Math.min(sc.titleAt - 0.3, a + 0.8));
      const dx = 540 - (X0 + TW_ / 2), dy = 700 - (TOP + TH_ / 2);
      tw(tile, a, 0.3, { o: [0, 1], s: [0.5, 1.6], x: [dx, dx], y: [dy, dy] }, 'back');
      tw(tile, mv, 0.34, { s: [1.6, 1], x: [dx, 0], y: [dy, 0] }, 'inOut');
      slide(ttl, Math.max(sc.titleAt, mv + 0.2), 0.3, 50);
      hb = TOP + TH_ + 12;
    } else {
      const ttl = el('div', 'ttl', rich(sc.title)); root.appendChild(ttl); ttl.style.top = TOP + 'px';
      const lh = parseFloat(getComputedStyle(ttl).fontSize) * 1.07;
      fitBox(ttl, W, lh * (first ? 3 : 2) + 6);
      if (!first) pop(ttl, sc.titleAt);
      hb = TOP + ttl.offsetHeight;
    }
    const blocks = sc.blocks || [];
    const col = el('div', 'col'); root.appendChild(col); col.style.top = (hb + 48) + 'px';
    const built = blocks.map(b => buildBlock(b, col, sc));
    const cadre = b => (b.kind === 'rush' || b.kind === 'avant_apres') ? (CADRE[b.cadre] ? b.cadre : 'paysage') : null;
    const forceB = blocks.some(b => cadre(b) === 'portrait' || cadre(b) === 'carre');
    const forceA = blocks.some(b => cadre(b) === 'paysage' || ['cartes', 'fenetre', 'chrono', 'mot', 'prompt', 'reponse'].includes(b.kind));
    let cb = blocks.length ? hb + 48 + col.offsetHeight : hb;
    let mode = 'A';
    if (forceB || (blocks.length && !forceA && FEET - cb - 26 < 470)) {
      mode = 'B'; col.classList.add('etroit');
      // avec une séquence verticale, toute la colonne prend la largeur du cadre : le personnage a le reste de l'écran
      const rw = Math.max(0, ...blocks.filter(b => cadre(b)).map(b => CADRE[cadre(b)][0] + 14));
      if (rw) col.style.width = rw + 'px';
    }
    built.forEach(x => x.fit());
    cb = blocks.length ? hb + 48 + col.offsetHeight : hb;
    built.forEach(x => x.anim());
    if (cb > TEXT_MAX) report.warnings.push(`écran ${idx + 1} : le contenu descend à ${Math.round(cb)} px (limite ${TEXT_MAX})`);

    const im = masc(sc.pose);
    if (im) {
      const p = im._p; let k, cx;
      if (mode === 'B') {
        // le personnage prend toute la place libre à droite de la colonne
        const colW = Math.max(0, ...built.map(x => x.e.offsetWidth)), free = 1080 - 16 - (X0 + colW + 20);
        k = Math.min(free / p.w, (FEET - hb - 16) / p.corps, 1.0); cx = X0 + colW + 20 + free / 2;
      }
      else { const avail = FEET - cb - 26; k = Math.min(avail / p.corps, 0.9); cx = 540; }
      if (k < 0.3) report.warnings.push(`écran ${idx + 1} : pas de place pour le personnage`);
      else {
        root.insertBefore(im, root.firstChild); placeMasc(im, k, cx);
        if (!first) tw(im, sc.poseAt != null ? sc.poseAt : t0 + 0.12, 0.36, { o: [0, 1], y: [90, 0] }, 'back');
        // le personnage réagit à chaque apparition d'un bloc
        blocks.forEach(b => { if (b.at != null && b.at > t0 + 0.6) bump(im, b.at + 0.05, 1.025); });
      }
    }
    return { mode, cb };
  }

  /* ---------------- écran de fin ---------------- */
  function buildFin(sc, root) {
    const t0 = sc.t0, panel = el('div', 'panel'); root.appendChild(panel);
    tw(panel, t0, 0.36, { y: [1920, 0] }, 'outExpo');
    const f1 = el('div', 'f1', 'Abonne-toi'); panel.appendChild(f1); pop(f1, t0 + 0.2);
    const btn = el('div', 'btn', "<span>S'abonner</span>"); panel.appendChild(btn); pop(btn, t0 + 0.42);
    const cur = el('div', 'cur', CURSOR); panel.appendChild(cur);
    const ck = sc.clickAt;
    tw(cur, ck - 0.62, 0.5, { o: [0, 1], x: [900, 672], y: [930, 548] }, 'inOut'); tw(cur, ck + 0.5, 0.3, { o: [1, 0] }, 'in');
    bump(btn, ck, 0.93);
    TICK.push(t => { const ok = t >= ck; if (btn._ok !== ok) { btn._ok = ok; btn.className = 'btn' + (ok ? ' ok' : ''); btn.innerHTML = ok ? `<span>Abonné</span>${CHECK}` : "<span>S'abonner</span>"; } });
    const box = el('div', 'box', `<small>Commente</small><div class="kw"><b></b><i class="caret"></i></div>`); panel.appendChild(box); pop(box, sc.boxAt);
    const kwb = $('.kw b', box), caret = $('.caret', box), kw = String(sc.keyword || '').toUpperCase();
    kwb.textContent = kw; fitW($('.kw', box), 820, 0.4); kwb.textContent = '';
    const k0 = sc.kwAt, kd = Math.min(0.5, 0.07 * kw.length + 0.1);
    TICK.push(t => {
      const cur_ = kw.slice(0, Math.round(clamp((t - k0) / kd) * kw.length)); if (kwb.textContent !== cur_) { kwb.textContent = cur_; kwb.style.display = cur_ ? '' : 'none'; }
      caret.style.visibility = (t < k0 + kd + 0.25) && Math.floor(Math.max(0, t - t0) / 0.3) % 2 === 0 ? 'inherit' : 'hidden';
    });
    bump(box, k0 + kd, 1.04);
    if (sc.promesse) { const g = el('div', 'egal', '= ' + rich(sc.promesse)); panel.appendChild(g); fitBox(g, 900, 124); pop(g, sc.promesseAt); }
    if (sc.promo) { const p = el('div', 'promo', `<span>${rich(sc.promo)}</span>`); panel.appendChild(p); if (!sc.promesse) p.style.top = '1060px'; p.style.whiteSpace = 'nowrap'; fitW($('span', p), 900, 0.5); rise(p, sc.promoAt); }
    if (TL.mention) { const m = el('div', 'mention', esc(TL.mention)); panel.appendChild(m); tw(m, t0 + 0.9, 0.4, { o: [0, 1] }, 'out'); }
    if (TL.handle) { const h = el('div', 'handle', esc(TL.handle)); panel.appendChild(h); fitW(h, 300); tw(h, t0 + 0.9, 0.4, { o: [0, 1] }, 'out'); }
    const im = masc(sc.pose || 'pouce');
    if (im) { panel.appendChild(im); placeMasc(im, 0.58, 540); tw(im, t0 + 0.34, 0.4, { o: [0, 1], y: [120, 0] }, 'back'); bump(im, k0 + kd, 1.04); }
  }

  /* ---------------- couverture ---------------- */
  function buildCover(cv) {
    const C = $('#cover'); C.appendChild(el('div', 'g'));
    const lines = (cv.lines || []).slice(0, 4), box = el('div', 'lines'); C.appendChild(box);
    lines.forEach((s, i) => { const hot = /\*/.test(s); const l = el('span', 'l' + (hot ? ' hot' : ''), `<span>${esc(String(s).replace(/\*/g, ''))}</span>`); box.appendChild(l); fitW(l, 980, 0.4); });
    const im = masc(cv.pose || 'pointe');
    if (im) { C.appendChild(im); const top = 190 + box.offsetHeight + 40; const k = Math.min((FEET + 40 - top) / im._p.corps, 1.15); placeMasc(im, k, 540); }
  }

  /* ---------------------------------------------------------------- */
  window.init = async function (tl) {
    TL = tl; DUR = tl.duration; TL.media = tl.media || {};
    const th = tl.theme || {}, rs = document.documentElement.style;
    for (const k in th) rs.setProperty('--' + k, th[k]);
    await Promise.all(['900 60px "Montserrat"', '800 60px "Montserrat"', '700 60px "Montserrat"', '600 60px "Montserrat"'].map(f => document.fonts.load(f)));
    await document.fonts.ready;
    const scenesRoot = $('#scenes');
    let fin = null;
    tl.scenes.forEach((sc, idx) => {
      const first = idx === 0, last = idx === tl.scenes.length - 1;
      const root = el('div', 'scene ' + sc.type); scenesRoot.appendChild(root);
      if (!first) tw(root, sc.t0, sc.type === 'fin' ? 0.01 : 0.14, { o: [0, 1] }, 'out');
      if (!last) tw(root, sc.t1 - 0.11, 0.11, { o: [1, 0] }, 'in');
      if (sc.type === 'fin') { buildFin(sc, root); fin = sc; } else buildEcran(sc, root, idx);
    });
    if (tl.cover) buildCover(tl.cover);

    // les images du personnage doivent être décodées avant la première capture
    await Promise.all([...document.querySelectorAll('img.masc')].map(im => (im.decode ? im.decode().catch(() => { report.warnings.push(`personnage : image « ${im._name} » illisible`); }) : Promise.resolve())));

    /* sous-titres */
    const C = $('#captions');
    const caps = (tl.captions || []).map(g => {
      const d = el('div', 'cap'); C.appendChild(d);
      const ws = g.words.map(w => { const s = el('span', 'w', esc(w.w)); d.appendChild(s); return { s, t: w.t, on: false }; });
      fitW(d, 1000, 0.5); d.style.visibility = 'hidden';
      return { d, ws, t0: g.t0, t1: g.t1, on: false };
    });
    TICK.push(t => {
      for (const g of caps) {
        const on = t >= g.t0 && t < g.t1;
        if (on !== g.on) { g.d.style.visibility = on ? 'visible' : 'hidden'; g.on = on; }
        if (!on) continue;
        for (let i = 0; i < g.ws.length; i++) {
          const w = g.ws[i], nx = g.ws[i + 1], cur = t >= w.t - 0.03 && (!nx || t < nx.t - 0.03);
          if (cur !== w.on) { w.on = cur; w.s.className = cur ? 'w on' : 'w'; }
        }
      }
      const inv = !!fin && t >= fin.t0 + 0.2; if (C._inv !== inv) { C._inv = inv; C.className = inv ? 'inv' : ''; }
    });
    const cover = $('#cover'); let cov = null;
    TICK.push(t => { const on = t < 0; if (on !== cov) { cov = on; cover.style.visibility = on ? 'visible' : 'hidden'; } });

    for (const it of ITEMS.values()) for (const k in it.p) it.p[k].sort((a, b) => a.t0 - b.t0);

    /* contrôle de mise en page : chaque écran dans son état final */
    document.querySelectorAll('.scene').forEach((s, i) => {
      const sc = tl.scenes[i];
      for (const it of ITEMS.values()) apply(it, Math.max(sc.t0, sc.t1 - 0.2));
      for (const f of TICK) f(Math.max(sc.t0, sc.t1 - 0.2));
      s.querySelectorAll('.ttl,.tuile,.bar,.row,.bx,.note,.ico,.chrono,.fen,.mot b,.mot span,.etq,.rush,.chips span,.f1,.btn,.box,.egal,.promo').forEach(e => {
        const r = e.getBoundingClientRect();
        if (!r.width) return;
        const name = (e.textContent || e.className).trim().slice(0, 28);
        if (r.left < 26 || r.right > 1054) report.warnings.push(`écran ${i + 1} : « ${name} » déborde (${Math.round(r.left)}–${Math.round(r.right)})`);
        if (sc.type !== 'fin' && r.bottom > TEXT_MAX + 6) report.warnings.push(`écran ${i + 1} : « ${name} » descend sous la zone lisible (${Math.round(r.bottom)})`);
      });
    });
    for (const it of ITEMS.values()) it.hidden = null;
    await window.renderAt(0);
    report.items = ITEMS.size; report.captions = caps.length; report.scenes = tl.scenes.length; report.media = Object.keys(TL.media).length;
    return report;
  };

  window.renderAt = async function (t) {
    for (const it of ITEMS.values()) apply(it, t);
    for (const f of TICK) f(t);
    if (ASYNC.length) await Promise.all(ASYNC.map(f => f(t)));
    return true;
  };
})();
