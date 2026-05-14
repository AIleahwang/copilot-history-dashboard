"""Her-style 'war room' spatial view — separate page at /space.
Reuses fetch_sessions() / categorize() / CAT_COLORS from server.py.
"""
import json, html as _html, os

def render_space(fetch_sessions, CAT_COLORS):
    sessions = fetch_sessions()
    total = len(sessions)
    for s in sessions:
        s['color'] = CAT_COLORS.get(s['cat'], '#a0aec0')
    cats = list(CAT_COLORS.keys())
    data_json = json.dumps(sessions, ensure_ascii=False)
    cat_color_json = json.dumps(CAT_COLORS, ensure_ascii=False)
    cat_order_json = json.dumps(cats, ensure_ascii=False)
    user_name = os.environ.get('USERNAME') or os.environ.get('USER') or 'My'
    title_name = user_name.capitalize() + "'s World"
    big_title_left = user_name.upper()
    return f"""<!doctype html><html lang=zh><head><meta charset=utf-8>
<title>{_html.escape(title_name)}</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
:root{{
  --warm-1:#f8b5a0; --warm-2:#e88a5e; --warm-3:#a8482c;
  --rose:#e87a8a; --peach:#f5a878; --amber:#ffd17a;
  --ink-1:#0f0807; --ink-2:#1a0e0c; --ink-3:#241510;
  --glass:rgba(40,22,18,.55);
  --glass-h:rgba(60,32,26,.7);
  --line:rgba(248,181,160,.18);
  --line-h:rgba(248,181,160,.45);
  --text:#fbeee5; --text-d:#d9beac; --text-m:#8e7468;
  --ok:#a8d4b8; --danger:#e8847a;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{height:100%;font-family:-apple-system,'Inter','PingFang SC','Microsoft YaHei',sans-serif;color:var(--text);overflow:hidden;background:var(--ink-1)}}
button{{font:inherit;color:inherit;background:none;border:none;cursor:pointer}}
@media (prefers-reduced-motion: reduce){{*{{animation-duration:.01s!important;transition-duration:.01s!important}}}}

/* ── The void ── */
#sky{{
  position:fixed;inset:0;z-index:0;
  background:
    radial-gradient(ellipse 60% 45% at 78% 18%, rgba(232,138,94,.55) 0%, rgba(232,138,94,.18) 38%, transparent 70%),
    radial-gradient(ellipse 70% 55% at 18% 88%, rgba(232,122,138,.30) 0%, rgba(168,72,44,.10) 45%, transparent 75%),
    radial-gradient(ellipse 40% 30% at 50% 50%, rgba(255,209,122,.10) 0%, transparent 60%),
    linear-gradient(180deg, var(--ink-2), var(--ink-1) 60%, #050203);
}}
#sky::before{{
  content:'';position:absolute;inset:0;
  background-image:
    linear-gradient(var(--line) 1px, transparent 1px),
    linear-gradient(90deg, var(--line) 1px, transparent 1px);
  background-size:80px 80px,80px 80px;
  mask-image:radial-gradient(ellipse 80% 80% at 50% 50%, #000 30%, transparent 75%);
  opacity:.35;
}}
#sky::after{{
  content:'';position:absolute;inset:0;
  background:radial-gradient(ellipse 50% 35% at 50% 100%, rgba(255,170,120,.18), transparent 70%);
  filter:blur(20px);
  animation:breathe 9s ease-in-out infinite;
}}
@keyframes breathe{{0%,100%{{opacity:.7;transform:translateY(0)}}50%{{opacity:1;transform:translateY(-12px)}}}}

/* drifting dust */
#dust{{position:fixed;inset:0;z-index:1;pointer-events:none;overflow:hidden}}
.mote{{position:absolute;width:3px;height:3px;border-radius:50%;background:#fff;opacity:0;animation:drift linear infinite;box-shadow:0 0 8px rgba(255,200,160,.8)}}
@keyframes drift{{0%{{opacity:0;transform:translateY(20px) translateX(0)}}10%{{opacity:.7}}90%{{opacity:.5}}100%{{opacity:0;transform:translateY(-110vh) translateX(40px)}}}}

/* ── Top bar ── */
.bar{{position:fixed;top:0;left:0;right:0;z-index:50;display:flex;align-items:center;gap:14px;padding:14px 24px;background:linear-gradient(180deg,rgba(15,8,7,.88),rgba(15,8,7,.4) 70%,transparent);backdrop-filter:blur(8px) saturate(1.1)}}
.bar h1{{font-size:14px;font-weight:500;letter-spacing:6px;text-transform:uppercase;color:var(--warm-1);text-shadow:0 0 12px rgba(248,181,160,.4)}}
.bar h1 span{{color:var(--warm-2);margin:0 4px}}
.bar .meta{{font-size:11px;letter-spacing:2px;color:var(--text-m);text-transform:uppercase}}
.spacer{{flex:1}}
.bar .toolbar{{display:flex;gap:8px}}
.tool{{padding:7px 14px;border-radius:100px;background:var(--glass);border:1px solid var(--line);color:var(--text-d);font-size:11.5px;letter-spacing:1.5px;text-transform:uppercase;transition:.2s}}
.tool:hover{{background:var(--glass-h);border-color:var(--line-h);color:var(--text)}}
.tool.active{{background:rgba(232,138,94,.18);border-color:var(--warm-2);color:var(--warm-1)}}

.search{{display:flex;align-items:center;gap:10px;background:var(--glass);border:1px solid var(--line);border-radius:100px;padding:8px 16px;width:280px;transition:.2s}}
.search:focus-within{{border-color:var(--warm-2);background:var(--glass-h);box-shadow:0 0 24px rgba(232,138,94,.2)}}
.search svg{{opacity:.5;flex-shrink:0}}
.search input{{flex:1;background:none;border:none;outline:none;color:var(--text);font-size:13px;letter-spacing:.3px}}
.search input::placeholder{{color:var(--text-m)}}

/* ── Stage ── */
#stage{{position:fixed;inset:54px 0 0 0;z-index:5;perspective:1800px;perspective-origin:50% 50%}}
#world{{position:absolute;inset:0;transform-style:preserve-3d;transition:transform .6s cubic-bezier(.2,.8,.2,1)}}

/* ── Floating panels (modules) ── */
.panel{{
  position:absolute;
  width:300px;
  background:linear-gradient(155deg,
    color-mix(in srgb, var(--c) 18%, var(--glass)) 0%,
    color-mix(in srgb, var(--c) 6%, var(--glass)) 100%);
  border:1px solid color-mix(in srgb, var(--c) 38%, var(--line));
  border-radius:18px;
  backdrop-filter:blur(14px) saturate(1.3);
  box-shadow:
    0 1px 0 rgba(255,255,255,.06) inset,
    0 0 0 1px color-mix(in srgb, var(--c) 12%, transparent) inset,
    0 24px 60px rgba(0,0,0,.45),
    0 0 60px color-mix(in srgb, var(--c) 18%, transparent);
  transition:box-shadow .3s, border-color .3s, transform .25s cubic-bezier(.2,.8,.2,1);
  display:flex;flex-direction:column;
  max-height:78vh;
}}
.panel.focused{{
  border-color:color-mix(in srgb, var(--c) 68%, var(--line));
  box-shadow:
    0 1px 0 rgba(255,255,255,.08) inset,
    0 0 0 1px color-mix(in srgb, var(--c) 22%, transparent) inset,
    0 24px 70px rgba(0,0,0,.5),
    0 0 90px color-mix(in srgb, var(--c) 32%, transparent);
  z-index:20;
}}
.panel.dimmed{{opacity:.42;filter:saturate(.6) blur(.4px)}}
.panel.dragging-self{{transition:none;cursor:grabbing}}
.panel.drop-here{{border-color:var(--c);box-shadow:0 0 0 2px var(--c), 0 0 60px color-mix(in srgb, var(--c) 50%, transparent)}}

.p-head{{
  padding:14px 16px 12px;cursor:grab;user-select:none;
  display:flex;align-items:center;gap:10px;
  border-bottom:1px solid color-mix(in srgb, var(--c) 22%, transparent);
}}
.p-head:active{{cursor:grabbing}}
.p-head .ic{{font-size:16px;filter:drop-shadow(0 0 6px color-mix(in srgb, var(--c) 60%, transparent))}}
.p-head .title{{flex:1;font-size:12px;font-weight:600;letter-spacing:2px;text-transform:uppercase;color:#fff;text-shadow:0 1px 0 rgba(0,0,0,.4)}}
.p-head .count{{font-size:10px;font-weight:700;letter-spacing:1px;color:color-mix(in srgb, var(--c) 30%, #fff);background:rgba(0,0,0,.25);padding:3px 8px;border-radius:100px;border:1px solid color-mix(in srgb, var(--c) 50%, transparent)}}

.p-body{{padding:10px 12px 14px;overflow-y:auto;flex:1;scrollbar-width:thin;scrollbar-color:var(--c) transparent}}
.p-body::-webkit-scrollbar{{width:6px}}
.p-body::-webkit-scrollbar-thumb{{background:color-mix(in srgb, var(--c) 35%, transparent);border-radius:3px}}
.p-empty{{font-size:11px;color:rgba(255,255,255,.4);font-style:italic;text-align:center;padding:18px 6px;letter-spacing:.5px}}

/* ── Cards (smaller, denser) ── */
.card{{position:relative;background:rgba(0,0,0,.32);border:1px solid color-mix(in srgb, var(--c) 22%, var(--line));border-radius:11px;padding:10px 12px;cursor:pointer;margin-bottom:8px;transition:.2s;overflow:hidden}}
.card::before{{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--c);opacity:.85}}
.card:hover{{background:rgba(0,0,0,.45);border-color:var(--c);transform:translateY(-1px);box-shadow:0 4px 16px color-mix(in srgb, var(--c) 30%, rgba(0,0,0,.4))}}
.card.dragging{{opacity:.4;transform:scale(.95)}}
.card.merge-target{{border:2px dashed var(--c);background:color-mix(in srgb, var(--c) 22%, rgba(0,0,0,.5));transform:scale(1.03)}}
.card h3{{font-size:13px;font-weight:600;line-height:1.35;color:var(--text);word-break:break-word;margin-bottom:4px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;max-height:5.4em}}
.card .ago{{font-size:10.5px;color:var(--text-m);letter-spacing:.4px}}
.card .ago.fresh{{color:var(--ok)}}
.card .pin{{position:absolute;top:6px;right:8px;font-size:10px;opacity:.85}}
.card .ask{{font-size:11.5px;color:var(--text-d);line-height:1.5;margin-top:6px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;opacity:.85}}
.card .snippet{{font-size:10.5px;color:var(--text-m);background:rgba(232,138,94,.08);border-left:2px solid var(--warm-2);padding:5px 7px;border-radius:0 5px 5px 0;margin-top:6px;line-height:1.45}}

mark{{background:rgba(232,138,94,.4);color:var(--text);border-radius:3px;padding:0 2px;font-weight:600}}

/* ── Resize handle ── */
.p-resize{{position:absolute;right:4px;bottom:4px;width:14px;height:14px;cursor:nwse-resize;opacity:.4;transition:.2s}}
.p-resize::before{{content:'';position:absolute;right:2px;bottom:2px;width:8px;height:8px;border-right:2px solid var(--c);border-bottom:2px solid var(--c);border-radius:0 0 4px 0}}
.panel:hover .p-resize{{opacity:.8}}

/* ── Toast ── */
#toast{{position:fixed;bottom:28px;left:50%;transform:translateX(-50%) translateY(30px);background:var(--ink-3);border:1px solid var(--line-h);color:var(--text);padding:11px 22px;border-radius:100px;font-size:12.5px;letter-spacing:.5px;opacity:0;transition:.3s;z-index:999;backdrop-filter:blur(10px)}}
#toast.show{{opacity:1;transform:translateX(-50%) translateY(0)}}
#toast.ok{{border-color:var(--ok)}}
#toast.err{{border-color:var(--danger);color:var(--danger)}}

/* ── Modal (PRD reuse) ── */
.backdrop{{position:fixed;inset:0;background:rgba(10,5,3,.82);backdrop-filter:blur(14px);z-index:90;display:none;align-items:flex-start;justify-content:center;padding:40px 20px;overflow-y:auto}}
.backdrop.show{{display:flex}}
.modal{{max-width:760px;width:100%;background:var(--ink-3);border:1px solid var(--line-h);border-radius:18px;overflow:hidden;box-shadow:0 24px 80px rgba(0,0,0,.7), 0 0 80px rgba(232,138,94,.12)}}
.m-head{{padding:24px 28px 18px;border-bottom:1px solid var(--line);position:relative}}
.m-head::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--c)}}
.m-head h2{{font-size:20px;font-weight:600;line-height:1.3;margin-bottom:8px}}
.m-head .meta{{font-size:11.5px;color:var(--text-m);letter-spacing:.5px;display:flex;gap:14px;flex-wrap:wrap}}
.m-body{{padding:20px 28px;max-height:60vh;overflow-y:auto}}
.m-body section{{margin-bottom:20px}}
.m-body h3{{font-size:10.5px;letter-spacing:2.5px;color:var(--text-m);text-transform:uppercase;font-weight:600;margin-bottom:10px}}
.m-body .purpose{{font-size:13.5px;line-height:1.7;background:rgba(0,0,0,.25);border-left:3px solid var(--c);padding:12px 14px;border-radius:8px;white-space:pre-wrap;word-break:break-word}}
.m-foot{{padding:14px 28px;border-top:1px solid var(--line);display:flex;gap:8px;flex-wrap:wrap;background:rgba(0,0,0,.2)}}
.btn{{padding:7px 14px;border-radius:100px;font-size:11.5px;letter-spacing:1px;text-transform:uppercase;background:var(--glass);border:1px solid var(--line);color:var(--text-d);transition:.2s}}
.btn:hover{{background:var(--glass-h);color:var(--text);border-color:var(--line-h)}}
.btn.primary{{background:rgba(232,138,94,.2);border-color:var(--warm-2);color:var(--warm-1)}}
.btn.primary:hover{{background:rgba(232,138,94,.32)}}
.btn.danger:hover{{background:rgba(232,132,122,.18);border-color:var(--danger);color:var(--danger)}}

/* ── Hint ── */
.hint{{position:fixed;bottom:18px;left:24px;z-index:50;font-size:10.5px;color:var(--text-m);letter-spacing:1px;line-height:1.6}}
.hint kbd{{background:var(--glass);border:1px solid var(--line);border-radius:4px;padding:1px 6px;font-size:10px;font-family:inherit;color:var(--text-d)}}
</style></head>
<body>
<div id=sky></div>
<div id=dust></div>

<div class=bar>
  <h1>{_html.escape(big_title_left)}<span>·</span>WORLD</h1>
  <span class=meta id=metaCount></span>
  <div class=spacer></div>
  <div class=search>
    <svg width=14 height=14 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2><circle cx=11 cy=11 r=7/><path d="m21 21-4.3-4.3"/></svg>
    <input id=q placeholder="搜索（中英双语）" autocomplete=off>
  </div>
  <div class=toolbar>
    <button class=tool id=btnLayout title="自动布局">⌘ Layout</button>
    <button class=tool onclick="location.href='/'">← 经典看板</button>
  </div>
</div>

<div id=stage><div id=world></div></div>

<div class=hint>
  拖<b>面板顶部</b>=移动模块 · 拖<b>右下角</b>=缩放 · 拖<b>卡片→另一卡片</b>=合并 · 拖<b>卡片→另一面板</b>=改分类 · <kbd>R</kbd>重置布局 · <kbd>F</kbd>聚焦
</div>

<div class=backdrop id=modal><div class=modal id=modalInner></div></div>
<div id=toast></div>

<script>
const DATA = {data_json};
const CAT_COLOR = {cat_color_json};
const CAT_ORDER = {cat_order_json};
const TOTAL = {total};
const PINS = new Set(JSON.parse(localStorage.getItem('pins')||'[]'));
const LAYOUT_KEY = 'space_layout_v1';
const state = {{q:'', focusCat:null}};

// ── Bilingual aliases (lite) ────
const ALIASES = {{
  '英语':['english','英文'],'english':['英语','英文'],'学习':['learn','learning','study'],'learn':['学习'],'learning':['学习'],
  '计划':['plan','planning'],'plan':['计划'],'客户':['customer','client'],'customer':['客户'],
  '商务':['business'],'business':['商务'],'技能':['skill','skills'],'skill':['技能'],
  '看板':['dashboard','board','kanban'],'dashboard':['看板'],'对话':['conversation','chat'],'chat':['对话'],
  '历史':['history'],'history':['历史'],'部署':['deploy','deployment'],'deploy':['部署'],
  '微信':['wechat','weixin'],'wechat':['微信'],'数字分身':['avatar','clone','twin','digital twin'],
  '汇报':['summary','report'],'summary':['汇报'],'老板':['boss','manager'],'模型':['model'],'model':['模型'],
  '可视化':['visualize','visualization'],'visualize':['可视化'],
}};
function expandTokens(q){{
  const tokens = q.toLowerCase().trim().split(/\\s+/).filter(Boolean);
  return tokens.map(tok => {{
    const v = new Set([tok]);
    (ALIASES[tok]||[]).forEach(a => v.add(a.toLowerCase()));
    for(const [k,vs] of Object.entries(ALIASES)){{ if(vs.map(x=>x.toLowerCase()).includes(tok)) v.add(k.toLowerCase()); }}
    return [...v];
  }});
}}
function matchQ(h, gs){{ const x = h.toLowerCase(); return gs.every(vs => vs.some(v => x.includes(v))); }}
function esc(s){{return (s||'').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]))}}
function highlight(t, q){{
  if(!q) return esc(t);
  const all = [...new Set(expandTokens(q).flat())].filter(x=>x).sort((a,b)=>b.length-a.length);
  if(!all.length) return esc(t);
  const re = new RegExp('('+all.map(s=>s.replace(/[.*+?^${{}}()|[\\]\\\\]/g,'\\\\$&')).join('|')+')','ig');
  return esc(t).replace(re,'<mark>$1</mark>');
}}
function daysAgo(iso){{
  const d=(Date.now()-new Date(iso).getTime())/86400000;
  if(d<1) return '今天'; if(d<2) return '昨天';
  if(d<7) return Math.floor(d)+'天前'; if(d<30) return Math.floor(d/7)+'周前';
  if(d<365) return Math.floor(d/30)+'月前'; return Math.floor(d/365)+'年前';
}}
function isFresh(iso){{ return (Date.now()-new Date(iso).getTime())/86400000 < 7; }}

// ── Filtering ──
function filtered(){{
  let arr = DATA.slice();
  if(state.q){{
    const gs = expandTokens(state.q);
    arr = arr.filter(s => matchQ(s.summary+' '+s.ask+' '+s.cat+' '+(s.body||''), gs));
  }}
  // Hide group members (only show primaries)
  arr = arr.filter(s => !s.group_id || s.is_primary);
  return arr;
}}

// ── Layout persistence ──
function loadLayout(){{
  try{{ return JSON.parse(localStorage.getItem(LAYOUT_KEY)||'{{}}'); }} catch(e){{ return {{}}; }}
}}
function saveLayout(l){{ localStorage.setItem(LAYOUT_KEY, JSON.stringify(l)); }}
function defaultLayout(){{
  // Spread cats in a graceful arc
  const W = window.innerWidth, H = window.innerHeight - 54;
  const out = {{}};
  CAT_ORDER.forEach((c, i) => {{
    const cols = 3, rows = 2;
    const col = i % cols, row = Math.floor(i / cols);
    const pw = 300, ph = Math.min(420, (H - 80) / rows - 20);
    const gx = (W - cols*pw - (cols-1)*20) / 2;
    const gy = 30;
    out[c] = {{x: gx + col*(pw+20), y: gy + row*(ph+20), w: pw, h: ph}};
  }});
  return out;
}}

// ── Render ──
function snippet(s, q){{
  if(!q || !s.body) return '';
  const gs = expandTokens(q);
  const head = (s.summary+' '+s.ask).toLowerCase();
  if(gs.every(vs=>vs.some(v=>head.includes(v)))) return '';
  if(!matchQ(s.body, gs)) return '';
  const all = [...new Set(gs.flat())].sort((a,b)=>b.length-a.length);
  const lower = s.body.toLowerCase();
  let pos=-1; for(const t of all){{ pos=lower.indexOf(t); if(pos>=0)break; }}
  if(pos<0) return '';
  const start = Math.max(0,pos-25), end = Math.min(s.body.length, pos+80);
  const sl = (start>0?'…':'')+s.body.slice(start,end)+(end<s.body.length?'…':'');
  return `<div class=snippet>💬 ${{highlight(sl,q)}}</div>`;
}}
function cardHTML(s){{
  const fresh = isFresh(s.updated_iso);
  const pinned = PINS.has(s.id);
  return `<article class=card style="--c:${{s.color}}" draggable=true data-id="${{s.id}}"
    ondragstart="cdStart(event,'${{s.id}}')" ondragend="cdEnd(event)"
    ondragover="cdOver(event,'${{s.id}}')" ondragleave="cdLeave(event)" ondrop="cdDrop(event,'${{s.id}}')"
    onclick="openModal('${{s.id}}')">
    ${{pinned?'<span class=pin>📌</span>':''}}
    <h3>${{highlight(s.summary, state.q)}}</h3>
    <div class=ago><span class="${{fresh?'fresh':''}}">${{daysAgo(s.updated_iso)}}</span> · ${{s.turns}}轮</div>
    ${{s.ask?`<div class=ask>${{highlight(s.ask, state.q)}}</div>`:''}}
    ${{snippet(s, state.q)}}
  </article>`;
}}

function render(){{
  const arr = filtered();
  document.getElementById('metaCount').textContent = `${{arr.length}} / ${{TOTAL}} 段记忆`;
  const layout = Object.assign({{}}, defaultLayout(), loadLayout());
  const byCat = {{}};
  CAT_ORDER.forEach(c => byCat[c] = []);
  arr.forEach(s => {{ if(byCat[s.cat]) byCat[s.cat].push(s); }});

  const w = document.getElementById('world');
  w.innerHTML = CAT_ORDER.map(c => {{
    const items = byCat[c] || [];
    const color = CAT_COLOR[c] || '#a0aec0';
    const pos = layout[c] || {{x:60, y:60, w:300, h:380}};
    const icon = c.split(' ')[0];
    const title = c.replace(/^[^\\s]+\\s*/, '');
    const cls = state.focusCat ? (state.focusCat===c?'focused':'dimmed') : '';
    return `<div class="panel ${{cls}}" style="--c:${{color}};left:${{pos.x}}px;top:${{pos.y}}px;width:${{pos.w}}px;height:${{pos.h}}px"
      data-cat="${{esc(c)}}"
      ondragover="pnDragOver(event)" ondragleave="pnDragLeave(event)" ondrop="pnDrop(event)">
      <div class=p-head onmousedown="pnGrab(event)" ondblclick="focusCat('${{esc(c)}}')">
        <span class=ic>${{icon}}</span>
        <span class=title>${{esc(title)}}</span>
        <span class=count>${{items.length}}</span>
      </div>
      <div class=p-body>${{items.length?items.map(cardHTML).join(''):'<div class=p-empty>无记忆</div>'}}</div>
      <div class=p-resize onmousedown="pnResize(event)"></div>
    </div>`;
  }}).join('');
}}

// ── Panel drag (move) ──
let _pnDrag = null;
function pnGrab(e){{
  if(e.button !== 0) return;
  const panel = e.currentTarget.parentElement;
  panel.classList.add('dragging-self');
  panel.style.zIndex = 30;
  _pnDrag = {{
    panel, cat: panel.dataset.cat,
    sx: e.clientX, sy: e.clientY,
    ox: parseInt(panel.style.left)||0, oy: parseInt(panel.style.top)||0,
  }};
  document.addEventListener('mousemove', _pnMove);
  document.addEventListener('mouseup', _pnDrop, {{once:true}});
  e.preventDefault();
}}
function _pnMove(e){{
  if(!_pnDrag) return;
  const dx = e.clientX - _pnDrag.sx, dy = e.clientY - _pnDrag.sy;
  let nx = _pnDrag.ox + dx, ny = Math.max(0, _pnDrag.oy + dy);
  const W = window.innerWidth, H = window.innerHeight - 54;
  nx = Math.max(-_pnDrag.panel.offsetWidth + 80, Math.min(W - 80, nx));
  ny = Math.min(H - 60, ny);
  _pnDrag.panel.style.left = nx+'px'; _pnDrag.panel.style.top = ny+'px';
}}
function _pnDrop(e){{
  if(!_pnDrag) return;
  document.removeEventListener('mousemove', _pnMove);
  _pnDrag.panel.classList.remove('dragging-self');
  _pnDrag.panel.style.zIndex = '';
  const layout = loadLayout();
  layout[_pnDrag.cat] = {{
    x: parseInt(_pnDrag.panel.style.left), y: parseInt(_pnDrag.panel.style.top),
    w: _pnDrag.panel.offsetWidth, h: _pnDrag.panel.offsetHeight
  }};
  saveLayout(layout);
  _pnDrag = null;
}}
// ── Panel resize ──
let _pnRz = null;
function pnResize(e){{
  e.stopPropagation();
  const panel = e.currentTarget.parentElement;
  _pnRz = {{panel, cat:panel.dataset.cat, sx:e.clientX, sy:e.clientY,
    ow:panel.offsetWidth, oh:panel.offsetHeight}};
  document.addEventListener('mousemove', _rzMove);
  document.addEventListener('mouseup', _rzDrop, {{once:true}});
  e.preventDefault();
}}
function _rzMove(e){{
  if(!_pnRz) return;
  const w = Math.max(220, _pnRz.ow + e.clientX - _pnRz.sx);
  const h = Math.max(180, _pnRz.oh + e.clientY - _pnRz.sy);
  _pnRz.panel.style.width = w+'px'; _pnRz.panel.style.height = h+'px';
}}
function _rzDrop(){{
  if(!_pnRz) return;
  document.removeEventListener('mousemove', _rzMove);
  const layout = loadLayout();
  const p = _pnRz.panel;
  layout[_pnRz.cat] = {{x:parseInt(p.style.left)||0, y:parseInt(p.style.top)||0, w:p.offsetWidth, h:p.offsetHeight}};
  saveLayout(layout);
  _pnRz = null;
}}

// ── Card drag: merge / recat ──
let DRAG_SID = null;
function cdStart(e, sid){{ DRAG_SID = sid; e.dataTransfer.effectAllowed='move'; e.dataTransfer.setData('text/plain', sid); e.currentTarget.classList.add('dragging'); }}
function cdEnd(){{
  document.querySelectorAll('.dragging,.merge-target,.drop-here').forEach(x=>x.classList.remove('dragging','merge-target','drop-here'));
  DRAG_SID = null;
}}
function cdOver(e, sid){{
  if(!DRAG_SID || DRAG_SID===sid) return;
  e.preventDefault(); e.stopPropagation();
  e.dataTransfer.dropEffect='move';
  e.currentTarget.classList.add('merge-target');
}}
function cdLeave(e){{ e.currentTarget.classList.remove('merge-target'); }}
async function cdDrop(e, tgt){{
  e.preventDefault(); e.stopPropagation();
  e.currentTarget.classList.remove('merge-target');
  if(!DRAG_SID || DRAG_SID===tgt) return;
  const src = DATA.find(x=>x.id===DRAG_SID), t = DATA.find(x=>x.id===tgt);
  if(!confirm(`将「${{src.summary}}」合并到「${{t.summary}}」？`)) return;
  const r = await fetch('/groups/merge',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{primary:tgt, secondary:DRAG_SID}})}});
  if(r.ok){{ toast('已合并 ✓','ok'); setTimeout(()=>location.reload(),350); }} else toast('合并失败','err');
}}
function pnDragOver(e){{ if(!DRAG_SID)return; e.preventDefault(); e.currentTarget.classList.add('drop-here'); }}
function pnDragLeave(e){{ if(e.currentTarget.contains(e.relatedTarget))return; e.currentTarget.classList.remove('drop-here'); }}
async function pnDrop(e){{
  e.preventDefault();
  const panel = e.currentTarget;
  panel.classList.remove('drop-here');
  const cat = panel.dataset.cat, sid = DRAG_SID;
  if(!sid || !cat) return;
  const src = DATA.find(x=>x.id===sid);
  if(!src || src.cat===cat) return;
  const r = await fetch('/sessions/recat',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{id:sid,cat}})}});
  if(r.ok){{ toast(`已移到「${{cat}}」 ✓`,'ok'); setTimeout(()=>location.reload(),350); }} else toast('移动失败','err');
}}

// ── Auto-scroll while dragging cards ──
let _sv = 0, _sr = null;
function _stick(){{ if(_sv){{ window.scrollBy(0,_sv); _sr=requestAnimationFrame(_stick); }} else _sr=null; }}
document.addEventListener('dragover', e=>{{
  if(!DRAG_SID) return;
  const y = e.clientY, h = window.innerHeight, edge=80;
  if(y<edge) _sv = -Math.ceil((edge-y)/4);
  else if(y>h-edge) _sv = Math.ceil((y-(h-edge))/4);
  else _sv = 0;
  if(_sv && !_sr) _sr = requestAnimationFrame(_stick);
}});
['dragend','drop'].forEach(ev => document.addEventListener(ev, ()=>_sv=0));

// ── Focus mode (Her: highlight one, dim rest) ──
function focusCat(c){{ state.focusCat = state.focusCat===c?null:c; render(); }}

// ── Modal (PRD) ──
async function openModal(id){{
  const m = document.getElementById('modal'), inner = document.getElementById('modalInner');
  inner.innerHTML = '<div style="padding:60px;text-align:center;color:var(--text-m)">⏳</div>';
  m.classList.add('show');
  let d; try{{ d = await (await fetch('/session?id='+id)).json(); }} catch(e){{ inner.innerHTML='<div style="padding:30px;color:var(--danger)">加载失败</div>'; return; }}
  inner.innerHTML = `
    <div class=m-head style="--c:${{d.cat_color}}">
      <h2>${{esc(d.summary)}}</h2>
      <div class=meta>
        <span>${{esc(d.cat)}}</span>·<span>${{d.turns}}轮</span>·<span>${{esc(d.status_label)}}</span>·<span>${{d.created_at.slice(0,10)}} → ${{d.updated_at.slice(0,10)}}</span>
      </div>
    </div>
    <div class=m-body>
      <section><h3>🎯 目的</h3><div class=purpose>${{esc(d.first_ask) || '(无首问)'}}</div></section>
      <section><h3>🔗 链路 · ${{d.chain.length}} 轮</h3>
        ${{d.chain.map(c=>`<div style="padding:7px 0;border-bottom:1px solid var(--line);font-size:12px"><b style="color:var(--text)">#${{c.i}}</b> <span style="opacity:.85">${{esc(c.user.slice(0,160))}}</span>${{c.has_reply?'':' <span style="color:var(--danger)">(无回复)</span>'}}</div>`).join('')}}
      </section>
      ${{d.artifacts.length?`<section><h3>📦 产出物 ${{d.artifacts.length}}</h3>${{d.artifacts.map(a=>`<div style="font-size:12px;padding:4px 0"><b>${{esc(a.path)}}</b> <span style="color:var(--text-m)">${{a.mtime}}</span></div>`).join('')}}</section>`:''}}
      ${{d.plan_preview?`<section><h3>📋 plan.md 预览</h3><div class=purpose style="font-family:'SF Mono',Consolas,monospace;font-size:11.5px;max-height:240px;overflow-y:auto">${{esc(d.plan_preview)}}</div></section>`:''}}
    </div>
    <div class=m-foot>
      <button class="btn primary" onclick="resume('${{d.id}}')">▶ 继续对话</button>
      <button class=btn onclick="closeModal()">关闭</button>
      <div style="flex:1"></div>
      <button class="btn danger" onclick="del_('${{d.id}}')">🗑 删除</button>
    </div>`;
}}
function closeModal(){{ document.getElementById('modal').classList.remove('show'); }}
document.getElementById('modal').addEventListener('click', e=>{{ if(e.target.id==='modal') closeModal(); }});

async function resume(id){{ const r = await fetch('/resume?id='+id,{{method:'POST'}}); toast(r.ok?'已新开窗口':'失败',r.ok?'ok':'err'); }}
async function del_(id){{ if(!confirm('删除？此操作不可逆')) return; const r = await fetch('/delete?id='+id,{{method:'POST'}}); if(r.ok){{ closeModal(); toast('已删除','ok'); setTimeout(()=>location.reload(),350); }} }}

// ── Toast ──
function toast(msg, kind){{ const t = document.getElementById('toast'); t.textContent = msg; t.className = (kind||'')+' show'; setTimeout(()=>t.classList.remove('show'),1800); }}

// ── Keyboard ──
document.addEventListener('keydown', e=>{{
  if(e.target.tagName==='INPUT') {{
    if(e.key==='Escape') e.target.blur();
    return;
  }}
  if(e.key==='/') {{ e.preventDefault(); document.getElementById('q').focus(); }}
  if(e.key==='Escape') closeModal();
  if(e.key==='r' || e.key==='R'){{ if(confirm('重置所有面板布局？')) {{ localStorage.removeItem(LAYOUT_KEY); render(); }} }}
  if(e.key==='f' || e.key==='F'){{ state.focusCat = state.focusCat?null:CAT_ORDER[0]; render(); }}
}});

// ── Search ──
document.getElementById('q').addEventListener('input', e=>{{ state.q = e.target.value; render(); }});
document.getElementById('btnLayout').addEventListener('click', ()=>{{ if(confirm('恢复默认布局？')){{ localStorage.removeItem(LAYOUT_KEY); render(); }} }});

// ── Particles ──
function initDust(){{
  const d = document.getElementById('dust');
  for(let i=0;i<30;i++){{
    const m = document.createElement('div');
    m.className = 'mote';
    m.style.left = Math.random()*100+'%';
    m.style.bottom = '-10px';
    m.style.animationDuration = (12 + Math.random()*16) + 's';
    m.style.animationDelay = (Math.random()*20)+'s';
    m.style.opacity = (0.3+Math.random()*0.5);
    m.style.transform = `scale(${{0.5+Math.random()*1.2}})`;
    d.appendChild(m);
  }}
}}

// ── Init ──
window.addEventListener('resize', () => {{
  // Keep panels visible if window shrinks
  const layout = loadLayout(); const W=window.innerWidth, H=window.innerHeight-54;
  Object.keys(layout).forEach(k=>{{
    if(layout[k].x > W-80) layout[k].x = W-100;
    if(layout[k].y > H-60) layout[k].y = H-80;
  }});
  saveLayout(layout); render();
}});
initDust();
render();
</script></body></html>"""
