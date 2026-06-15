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
.panel-more{{width:100%;margin:4px 0 2px;padding:8px 10px;border-radius:10px;border:1px dashed color-mix(in srgb,var(--c) 45%,transparent);background:color-mix(in srgb,var(--c) 11%,rgba(0,0,0,.26));color:color-mix(in srgb,var(--c) 40%,#fff);font-size:11px;letter-spacing:.8px}}
.panel-more:hover{{border-style:solid;background:color-mix(in srgb,var(--c) 18%,rgba(0,0,0,.32));color:#fff}}

/* ── Cards (smaller, denser) ── */
.card{{position:relative;background:color-mix(in srgb, var(--c) 10%, rgba(0,0,0,.34));border:1px solid color-mix(in srgb, var(--c) 24%, var(--line));border-radius:14px;padding:12px;cursor:pointer;margin-bottom:9px;transition:.2s;overflow:hidden}}
.card::before{{content:'';position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--c);opacity:.9}}
.card:hover{{background:color-mix(in srgb, var(--c) 13%, rgba(0,0,0,.46));border-color:var(--c);transform:translateY(-1px);box-shadow:0 4px 16px color-mix(in srgb, var(--c) 30%, rgba(0,0,0,.4))}}
.card.pinned{{border-color:rgba(255,211,122,.55)}}
.card.pinned::after{{content:'📌';position:absolute;top:9px;right:9px;font-size:11px;opacity:.85}}
.card.stale{{opacity:.58}}
.card.stale:hover{{opacity:1}}
.card.done{{animation:missionDone .55s ease forwards;pointer-events:none}}
.card.dragging{{opacity:.4;transform:scale(.95)}}
.card.merge-target{{border:2px dashed var(--c);background:color-mix(in srgb, var(--c) 22%, rgba(0,0,0,.5));transform:scale(1.03)}}
.card-head{{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:7px}}
.card h3{{font-size:13.5px;font-weight:650;line-height:1.35;color:var(--text);word-break:break-word;padding-right:22px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;max-height:5.4em}}
.card .meta{{display:flex;gap:7px;align-items:center;font-size:10.5px;color:var(--text-m);margin-bottom:8px;letter-spacing:.3px;flex-wrap:wrap}}
.card .meta .sep{{opacity:.5}}
.card .ago{{color:var(--text-d);font-weight:500}}
.card .ago.fresh{{color:var(--ok)}}
.card .pin{{position:absolute;top:6px;right:8px;font-size:10px;opacity:.85}}
.card .ask{{font-size:11.5px;color:var(--text-d);line-height:1.5;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;margin-bottom:10px;opacity:.9}}
.card .ask:empty::before,.card .ask .empty{{content:'(无首问)';color:var(--text-m);font-style:italic}}
.card .snippet{{font-size:10.5px;color:var(--text-m);background:rgba(232,138,94,.08);border-left:2px solid var(--warm-2);padding:5px 7px;border-radius:0 5px 5px 0;margin-bottom:8px;line-height:1.45}}
.card footer{{display:flex;gap:6px;align-items:center;flex-wrap:wrap;position:relative;z-index:2}}
.btn{{padding:6px 9px;border-radius:8px;font-size:11px;letter-spacing:.4px;color:var(--text-d);background:transparent;border:1px solid rgba(255,255,255,.12);transition:.15s;font-weight:500}}
.btn:hover{{background:rgba(255,255,255,.06);color:var(--text);border-color:var(--line-h)}}
.btn.primary{{color:var(--warm-1);border-color:rgba(232,138,94,.35)}}
.btn.primary:hover{{background:rgba(232,138,94,.14);border-color:var(--warm-2)}}
.btn.danger:hover{{background:rgba(232,132,122,.15);border-color:var(--danger);color:var(--danger)}}
.btn.icon{{padding:6px 8px;font-size:12px}}
.btn.done{{color:#9FE870;border-color:rgba(159,232,112,.35)}}
.btn.done:hover{{background:rgba(159,232,112,.13);border-color:#9FE870;color:#fff}}
.group-badge,.mission-badge{{display:inline-flex;align-items:center;gap:5px;color:#fff;font-size:10px;font-weight:800;letter-spacing:.7px;padding:2px 8px;border-radius:100px;margin-bottom:6px;border:1px solid color-mix(in srgb,var(--c) 58%,transparent);background:color-mix(in srgb,var(--c) 34%,transparent)}}
.mission-badge{{border-color:color-mix(in srgb,var(--p,#9FE870) 62%,transparent);background:color-mix(in srgb,var(--p,#9FE870) 30%,rgba(0,0,0,.24));color:#fff;text-transform:uppercase}}
.group-members{{display:flex;flex-direction:column;gap:6px;margin:8px 0 10px;padding:8px;background:rgba(0,0,0,.18);border-radius:8px;border:1px solid rgba(255,255,255,.1);max-height:160px;overflow-y:auto;scrollbar-width:thin;scrollbar-color:var(--c) transparent}}
.group-member{{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:5px 8px;border-radius:6px;font-size:11px;color:var(--text-d);transition:.15s;cursor:default}}
.group-member:hover{{background:rgba(255,255,255,.05)}}
.group-member .name{{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.group-member .pop{{opacity:0;transition:.15s;font-size:14px;line-height:1;color:var(--text-m);padding:2px 6px;border-radius:4px;cursor:pointer}}
.group-member:hover .pop{{opacity:1}}
.group-member .pop:hover{{background:rgba(232,132,122,.15);color:var(--danger)}}

/* ── Mission Queue: floating priority radar ── */
.mission-layer{{position:absolute;inset:0;z-index:35;pointer-events:none}}
.mission-layer.hidden{{display:none}}
.mission-panel{{
  position:absolute;width:350px;max-height:420px;display:block;overflow:hidden;border-radius:20px;
  background:linear-gradient(155deg,rgba(20,14,12,.76),rgba(64,34,26,.45));
  border:1px solid rgba(255,209,122,.26);
  box-shadow:0 18px 58px rgba(0,0,0,.46),0 0 70px rgba(255,209,122,.08),inset 0 1px 0 rgba(255,255,255,.06);
  backdrop-filter:blur(16px) saturate(1.35);pointer-events:auto;isolation:isolate;
}}
.mission-panel:hover{{z-index:60}}
.mission-panel.dragging-self{{transition:none;cursor:grabbing;z-index:80}}
.mission-panel.drop-here{{border-color:var(--p,#9FE870);box-shadow:0 0 0 2px var(--p,#9FE870),0 0 70px color-mix(in srgb,var(--p,#9FE870) 45%,transparent)}}
.mission-head{{padding:13px 15px 10px;display:flex;align-items:center;gap:9px;border-bottom:1px solid rgba(255,209,122,.14);cursor:grab;user-select:none}}
.mission-head:active{{cursor:grabbing}}
.mission-orb{{width:13px;height:13px;border-radius:50%;background:radial-gradient(circle,#fff 0,#9FE870 38%,#22d3a8 75%);box-shadow:0 0 18px rgba(159,232,112,.8)}}
.mission-title{{flex:1;font-size:12px;font-weight:700;letter-spacing:2.2px;text-transform:uppercase;color:#fff}}
.mission-count{{font-size:10px;color:var(--amber);border:1px solid rgba(255,209,122,.34);border-radius:100px;padding:2px 8px;background:rgba(0,0,0,.22)}}
.mission-body{{padding:10px 12px 66px;max-height:375px;overflow-y:auto;overflow-x:hidden;scrollbar-width:thin;scrollbar-color:rgba(255,209,122,.5) transparent;position:relative;z-index:1}}
.mission-body::-webkit-scrollbar{{width:6px}}
.mission-body::-webkit-scrollbar-thumb{{background:rgba(255,209,122,.42);border-radius:3px}}
.mission-card{{position:relative;margin-bottom:8px;padding:10px 10px 10px 12px;border-radius:13px;background:rgba(0,0,0,.32);border:1px solid rgba(255,255,255,.12);cursor:pointer;transition:.2s;overflow:hidden}}
.mission-card::before{{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--p,#9FE870)}}
.mission-card:hover{{transform:translateY(-1px);border-color:var(--p,#9FE870);box-shadow:0 8px 24px rgba(0,0,0,.32),0 0 26px color-mix(in srgb,var(--p,#9FE870) 22%,transparent)}}
.mission-card.selected{{border-color:var(--p,#9FE870);box-shadow:0 0 0 1px var(--p,#9FE870),0 0 34px color-mix(in srgb,var(--p,#9FE870) 28%,transparent)}}
.mission-card.done{{animation:missionDone .55s ease forwards}}
.mission-card.dragging{{opacity:.45;transform:scale(.96)}}
@keyframes missionDone{{to{{opacity:0;transform:translateX(34px) scale(.92);filter:blur(4px)}}}}
.mission-top{{display:flex;align-items:center;gap:7px;margin-bottom:6px}}
.mission-pri{{font-size:9px;font-weight:800;letter-spacing:.8px;color:#050203;background:var(--p,#9FE870);border-radius:6px;padding:2px 5px}}
.mission-kind{{font-size:9px;color:var(--text-m);text-transform:uppercase;letter-spacing:1px}}
.mission-name{{font-size:12.5px;font-weight:700;line-height:1.35;color:var(--text);margin-bottom:5px}}
.mission-next{{font-size:11.5px;line-height:1.5;color:var(--text-d);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.mission-cadence{{font-size:10.5px;color:var(--amber);margin-top:6px;opacity:.85}}
.mission-tools{{display:flex;gap:5px;margin-top:8px}}
.mission-tools button{{font-size:10.5px;padding:4px 7px;border-radius:8px;border:1px solid rgba(255,255,255,.12);color:var(--text-d);background:rgba(255,255,255,.04)}}
.mission-tools button:hover{{border-color:var(--p,#9FE870);color:#fff}}
.mission-more{{width:100%;padding:6px 8px;border-radius:10px;border:1px dashed rgba(255,209,122,.24);background:rgba(255,209,122,.06);color:var(--amber);font-size:10.5px;letter-spacing:.8px}}
.mission-more:hover{{border-style:solid;background:rgba(255,209,122,.11);color:#fff}}
.mission-actions{{display:flex;gap:8px;padding:8px 10px 10px;border-top:1px solid rgba(255,209,122,.12);position:absolute;left:0;right:0;bottom:0;z-index:50;background:rgba(20,14,12,.94);backdrop-filter:blur(10px);box-shadow:0 -10px 22px rgba(0,0,0,.26)}}
.mission-actions button{{position:relative;z-index:51}}
.mission-actions button{{flex:1;font-size:10.5px;letter-spacing:1px;text-transform:uppercase;padding:6px 8px;border-radius:100px;border:1px solid rgba(255,209,122,.24);background:rgba(255,209,122,.08);color:var(--amber)}}
.mission-empty{{padding:20px 12px;text-align:center;color:var(--text-m);font-size:12px;line-height:1.6}}
.mission-note{{font-size:11px;line-height:1.55;color:var(--text-d);background:rgba(255,209,122,.06);border:1px solid rgba(255,209,122,.14);border-radius:12px;padding:9px 10px;margin-bottom:8px}}
.mission-note b{{display:block;color:#fff;margin-bottom:4px}}
#missionFx{{position:fixed;inset:0;z-index:9999;pointer-events:none}}

/* Category picker dropdown (same behavior as main board) */
.cat-picker{{background:var(--ink-3);border:1px solid var(--line-h);border-radius:12px;padding:6px;box-shadow:0 12px 40px rgba(0,0,0,.5);min-width:200px;animation:cp-in .15s ease-out}}
@keyframes cp-in{{from{{opacity:0;transform:translateY(-4px)}}to{{opacity:1;transform:translateY(0)}}}}
.cat-picker .cp-title{{font-size:10px;letter-spacing:1.5px;color:var(--text-m);text-transform:uppercase;padding:6px 10px 8px}}
.cat-picker .cp-item{{display:flex;align-items:center;gap:9px;width:100%;padding:8px 10px;border-radius:8px;font-size:12.5px;color:var(--text-d);background:transparent;border:none;text-align:left;transition:.12s;cursor:pointer}}
.cat-picker .cp-item:hover{{background:color-mix(in srgb, var(--c) 18%, transparent);color:var(--text)}}
.cat-picker .cp-item.cur{{color:var(--text);background:rgba(255,255,255,.04)}}
.cat-picker .cp-item .dot{{width:8px;height:8px;border-radius:50%;background:var(--c);flex-shrink:0}}
.cat-picker .cp-item .tag{{font-size:9px;color:var(--text-m);margin-left:auto;letter-spacing:1px;text-transform:uppercase}}

/* Existing-task picker for +Mission */
.mission-picker{{max-width:920px}}
.mp-tools{{display:flex;gap:10px;align-items:center;margin-bottom:12px}}
.mp-tools input{{flex:1;background:rgba(0,0,0,.22);border:1px solid var(--line);border-radius:12px;color:var(--text);padding:10px 12px;outline:none}}
.mp-list{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;max-height:58vh;overflow-y:auto;padding-right:4px;scrollbar-width:thin;scrollbar-color:var(--warm-2) transparent}}
.mp-item{{display:flex;gap:9px;align-items:flex-start;border:1px solid rgba(255,255,255,.1);border-radius:12px;background:rgba(0,0,0,.24);padding:10px;cursor:pointer;transition:.15s}}
.mp-item:hover{{border-color:var(--warm-2);background:rgba(232,138,94,.08)}}
.mp-item input{{margin-top:3px;accent-color:#9FE870}}
.mp-title{{font-size:12.5px;font-weight:700;line-height:1.35;color:var(--text);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.mp-meta{{font-size:10.5px;color:var(--text-m);margin-top:4px}}
.mp-ask{{font-size:11px;color:var(--text-d);line-height:1.45;margin-top:5px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}

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
    <svg width=14 height=14 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2><circle cx=11 cy=11 r="7"/><path d="m21 21-4.3-4.3"/></svg>
    <input id=q placeholder="搜索（中英双语）" autocomplete=off>
  </div>
  <div class=toolbar>
    <button class=tool id=btnMission title="任务雷达">Mission</button>
    <button class=tool onclick="location.href='/'">← 经典看板</button>
  </div>
</div>

<div id=stage><div id=world></div><div id=missionLayer class=mission-layer></div></div>
<canvas id=missionFx></canvas>

<div class=hint>
  作战空间只显示 <b>Mission 漂浮模块</b> · 模块内嵌相关主看板任务 · <b>+Mission</b>=勾选已有任务 · <kbd>R</kbd>重置空间
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
const PANEL_EXPANDED_KEY = 'space_panel_expanded_v1';
const PANEL_LIMIT = 6;
const state = {{q:'', focusCat:null}};
const PANEL_EXPANDED = new Set(JSON.parse(localStorage.getItem(PANEL_EXPANDED_KEY)||'[]'));

// ── Mission Queue ───────────────────────────────────────────────
let MISSIONS = [];
let SELECTED_MISSION_ID = null;
const MQ_LAYOUT_KEY = 'mission_dock_layout_v3';
const LANE_LABEL = {{NOW:'NOW · 今日推进', NEXT:'NEXT · 本周排期', LOOP:'LOOP · 循环任务', PARKED:'PARKED · 暂停观察'}};
const LANE_ORDER = ['NOW','NEXT','LOOP','PARKED'];
const LANE_LIMIT = {{NOW:5, NEXT:5, LOOP:5, PARKED:5}};
const MQ_LANE_EXPANDED_KEY = 'mission_lane_expanded_v1';
const MQ_LANE_EXPANDED = new Set(JSON.parse(localStorage.getItem(MQ_LANE_EXPANDED_KEY)||'[]'));
const PRI_COLOR = {{P0:'#9FE870', P1:'#FFD17A', P2:'#a78bfa'}};
const PRI_RANK = {{P0:0, P1:1, P2:2}};

function missionActive(){{ return MISSIONS.filter(m => m.status !== 'completed'); }}
function missionSort(a,b){{ return (PRI_RANK[a.priority]??9)-(PRI_RANK[b.priority]??9) || (a.sort_order??0)-(b.sort_order??0) || a.title.localeCompare(b.title); }}
function missionHTML(m){{
  const color = PRI_COLOR[m.priority] || '#9FE870';
  const kind = m.type === 'loop' ? 'loop' : 'project';
  return `<article class="mission-card ${{SELECTED_MISSION_ID===m.id?'selected':''}}" style="--p:${{color}}" data-mid="${{esc(m.id)}}" onclick="focusMission('${{esc(m.id)}}')">
    <div class=mission-top><span class=mission-pri>${{esc(m.priority)}}</span><span class=mission-kind>${{kind}}</span></div>
    <div class=mission-name>${{esc(m.title)}}</div>
    <div class=mission-next>${{esc(m.next || '写下下一步，让任务能闭环')}}</div>
    ${{m.cadence?`<div class=mission-cadence>⏱ ${{esc(m.cadence)}}</div>`:''}}
    <div class=mission-tools>
      <button onclick="completeMission(event,'${{esc(m.id)}}')">闭环</button>
      <button onclick="editMission(event,'${{esc(m.id)}}')">改</button>
      <button onclick="deleteMission(event,'${{esc(m.id)}}')">删</button>
    </div>
  </article>`;
}}
function loadMissionLayout(){{
  try{{ return JSON.parse(localStorage.getItem(MQ_LAYOUT_KEY)||'{{}}'); }}catch(e){{ return {{}}; }}
}}
function saveMissionLayout(l){{ localStorage.setItem(MQ_LAYOUT_KEY, JSON.stringify(l)); }}
function defaultLanePos(lane, i){{
  const W = innerWidth, H = innerHeight - 54;
  const cols = Math.max(2, Math.floor(W / 365));
  const col = i % cols;
  const row = Math.floor(i / cols);
  const jitter = (lane.charCodeAt(0) % 17) - 8;
  return {{
    x: Math.max(18, Math.min(W - 365, 28 + col * 365 + jitter)),
    y: Math.max(20, Math.min(H - 430, 38 + row * 430 + (i % 2) * 18)),
  }};
}}
function topLevelSessions(){{
  return DATA.filter(s => !s.group_id || s.is_primary)
    .sort((a,b) => {{
      const pa=PINS.has(a.id), pb=PINS.has(b.id);
      if(pa!==pb) return pb-pa;
      return new Date(b.updated_iso)-new Date(a.updated_iso);
    }});
}}
function sessionsForMission(m){{
  const all = topLevelSessions();
  if(m.session_id){{
    const one = all.find(s => s.id === m.session_id);
    return one && !(m.done_session_ids || []).includes(one.id) ? [one] : [];
  }}
  const done = new Set(m.done_session_ids || []);
  return all.filter(s => missionMatchesSession(m, s) && !done.has(s.id)).slice(0, 2);
}}
function missionVisible(m){{
  if(!state.q) return true;
  const q = state.q.toLowerCase().trim();
  const own = (m.title+' '+m.next+' '+m.query+' '+m.lane+' '+m.priority).toLowerCase();
  if(own.includes(q)) return true;
  return sessionsForMission(m).some(s => (s.summary+' '+s.ask+' '+s.cat+' '+(s.body||'')).toLowerCase().includes(q));
}}
function missionTaskHTML(m){{
  const color = PRI_COLOR[m.priority] || '#9FE870';
  const sessions = sessionsForMission(m);
  return `<article class="mission-card ${{SELECTED_MISSION_ID===m.id?'selected':''}}" style="--p:${{color}}" data-mid="${{esc(m.id)}}"
   draggable=true ondragstart="mtStart(event,'${{esc(m.id)}}')" ondragend="mtEnd(event)" onclick="focusMission('${{esc(m.id)}}')">
   <div class=mission-top><span class=mission-pri>${{esc(m.priority)}}</span><span class=mission-kind>${{m.type==='loop'?'loop':'project'}}</span></div>
   <div class=mission-name>${{esc(m.title)}}</div>
   <div class=mission-next>${{esc(m.next || '写下下一步，让任务能闭环')}}</div>
   ${{m.cadence?`<div class=mission-cadence>⏱ ${{esc(m.cadence)}}</div>`:''}}
   ${{sessions.length ? sessions.map(s => cardHTML(s, m)).join('') : `<div class=mission-note><b>未绑定主看板任务</b><span>${{esc(m.next || '用 +Mission 勾选一个已有任务，或编辑关键词来关联。')}}</span></div>`}}
   <div class=mission-tools>
     <button onclick="completeMission(event,'${{esc(m.id)}}')">Done</button>
     <button onclick="editMission(event,'${{esc(m.id)}}')">Edit</button>
     <button onclick="deleteMission(event,'${{esc(m.id)}}')">Del</button>
   </div>
  </article>`;
}}
function missionPanelHTML(lane, items, i, layout){{
  const pos = layout[lane] || defaultLanePos(lane, i);
  const laneColor = items[0] ? (PRI_COLOR[items[0].priority] || '#FFD17A') : '#FFD17A';
  const expanded = MQ_LANE_EXPANDED.has(lane);
  const limit = LANE_LIMIT[lane] || 5;
  const shown = expanded ? items : items.slice(0, limit);
  const hidden = Math.max(0, items.length - shown.length);
  return `<section class=mission-panel style="--p:${{laneColor}};left:${{pos.x}}px;top:${{pos.y}}px" data-lane="${{lane}}"
   ondragover="laneDragOver(event)" ondragleave="laneDragLeave(event)" ondrop="laneDrop(event)">
    <div class=mission-head onmousedown="mpGrab(event)">
      <span class=mission-orb></span>
     <span class=mission-title>${{LANE_LABEL[lane]}}</span>
     <span class=mission-count>${{items.length}}</span>
    </div>
    <div class=mission-body>
     ${{shown.length ? shown.map(missionTaskHTML).join('') : '<div class=mission-empty>空轨道 · 可拖任务到这里</div>'}}
     ${{hidden ? `<button class=mission-more onclick="toggleMissionLane(event,'${{lane}}')">+${{hidden}} more</button>` : ''}}
     ${{expanded && items.length>limit ? `<button class=mission-more onclick="toggleMissionLane(event,'${{lane}}')">收起到 ${{limit}} 个</button>` : ''}}
    </div>
    <div class=mission-actions>
     <button onclick="openMissionPicker(event,'${{lane}}')">+ Mission</button>
     <button onclick="toggleMissionLane(event,'${{lane}}')">${{expanded?'Collapse':'Expand'}}</button>
    </div>
  </section>`;
}}
function renderMissions(){{
  const layer = document.getElementById('missionLayer');
  const active = missionActive().filter(missionVisible);
  const layout = loadMissionLayout();
  layer.innerHTML = LANE_ORDER.map((lane, i) => {{
   const items = active.filter(m => m.lane === lane).sort(missionSort);
   return missionPanelHTML(lane, items, i, layout);
  }}).join('');
}}
function toggleMissionLane(e, lane){{
  e.stopPropagation();
  if(MQ_LANE_EXPANDED.has(lane)) MQ_LANE_EXPANDED.delete(lane); else MQ_LANE_EXPANDED.add(lane);
  localStorage.setItem(MQ_LANE_EXPANDED_KEY, JSON.stringify([...MQ_LANE_EXPANDED]));
  renderMissions();
}}
async function loadMissions(){{
  try{{
    const r = await fetch('/missions');
    const j = await r.json();
    MISSIONS = Array.isArray(j.missions) ? j.missions : [];
    renderMissions();
    render();
  }}catch(e){{ document.getElementById('missionLayer').innerHTML = '<section class=mission-panel style="left:60px;top:90px"><div class=mission-body><div class=mission-empty>任务雷达加载失败</div></div></section>'; }}
}}
async function saveMission(m){{
  const r = await fetch('/missions/upsert', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(m)}});
  if(!r.ok) throw new Error('save failed');
  const j = await r.json(); MISSIONS = j.missions || MISSIONS; renderMissions(); render();
}}
function focusMission(id){{
  const m = MISSIONS.find(x => x.id === id); if(!m) return;
  if(m.session_id){{ openModal(m.session_id); return; }}
  SELECTED_MISSION_ID = SELECTED_MISSION_ID === id ? null : id;
  renderMissions();
  render();
  toast(`已高亮：${{m.title}}`,'ok');
}}
async function completeMission(e,id){{
  e.stopPropagation();
  const card = e.currentTarget.closest('.mission-card');
  const rect = card ? card.getBoundingClientRect() : null;
  const r = await fetch('/missions/complete', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{id}})}});
  if(r.ok){{
    missionSpark(rect);
    if(card) card.classList.add('done');
    setTimeout(async()=>{{ await loadMissions(); toast('✨ 闭环 +1 · 熵 -1','ok'); }}, 420);
  }} else toast('闭环失败','err');
}}
async function completeMissionSession(e, missionId, sessionId){{
  e.stopPropagation();
  const card = e.currentTarget.closest('.card');
  const rect = card ? card.getBoundingClientRect() : null;
  const r = await fetch('/missions/session-done', {{method:'POST',
    headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{id: missionId, session_id: sessionId}})}});
  if(r.ok){{
    missionSpark(rect);
    if(card) card.classList.add('done');
    setTimeout(async()=>{{ await loadMissions(); toast('🏆 小任务完成 · +1 胜利','ok'); }}, 420);
  }} else toast('完成失败','err');
}}
async function deleteMission(e,id){{
  e.stopPropagation();
  const m = MISSIONS.find(x => x.id === id); if(!m) return;
  if(!confirm(`删除任务「${{m.title}}」？`)) return;
  const r = await fetch('/missions/delete', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{id}})}});
  if(r.ok){{ await loadMissions(); toast('已移除任务','ok'); }} else toast('删除失败','err');
}}
async function editMission(e,id){{
  e.stopPropagation();
  const m = MISSIONS.find(x => x.id === id); if(!m) return;
  const title = prompt('任务标题', m.title); if(!title) return;
  const lane = (prompt('轨道：NOW / NEXT / LOOP / PARKED', m.lane) || m.lane).toUpperCase();
  const priority = (prompt('优先级：P0 / P1 / P2', m.priority) || m.priority).toUpperCase();
  const cadence = prompt('节奏 / 截止', m.cadence || '') ?? m.cadence;
  const next = prompt('下一步动作', m.next || '') ?? m.next;
  const query = prompt('点击后搜索关键词', m.query || title) ?? m.query;
  try{{ await saveMission({{...m,title,lane,priority,cadence,next,query}}); toast('任务已更新','ok'); }}catch(err){{ toast('保存失败','err'); }}
}}
async function newMission(e, defaultLane){{
  e.stopPropagation();
  const title = prompt('新任务标题'); if(!title) return;
  const lane = (prompt('轨道：NOW / NEXT / LOOP / PARKED', defaultLane || 'NEXT') || defaultLane || 'NEXT').toUpperCase();
  const priority = (prompt('优先级：P0 / P1 / P2', 'P1') || 'P1').toUpperCase();
  const cadence = prompt('节奏 / 截止（例如：本周五 / 每两周）', '') || '';
  const next = prompt('下一步动作', '') || '';
  const query = prompt('点击后搜索关键词', title) || title;
  try{{ await saveMission({{title,lane,priority,cadence,next,query,type:lane==='LOOP'?'loop':'project'}}); toast('Mission 已加入轨道','ok'); }}catch(err){{ toast('保存失败','err'); }}
}}
function linkedMissionForSession(sid){{ return MISSIONS.find(m => m.session_id === sid && m.status !== 'completed') || null; }}
function missionIdForSession(sid){{ return 'session-' + sid.replace(/[^A-Za-z0-9_-]/g, '-'); }}
function missionPickerRows(defaultLane, q=''){{
  const query = q.trim().toLowerCase();
  return topLevelSessions().filter(s => {{
    if(!query) return true;
    return (s.summary+' '+s.ask+' '+s.cat+' '+(s.body||'')).toLowerCase().includes(query);
  }}).map(s => {{
    const linked = linkedMissionForSession(s.id);
    const pri = linked ? linked.priority : 'P1';
    const lane = linked ? linked.lane : (defaultLane || 'NOW');
    return `<label class=mp-item data-hay="${{esc((s.summary+' '+s.ask+' '+s.cat).toLowerCase())}}">
      <input type=checkbox ${{linked?'checked':''}} onchange="toggleSessionMission(event,'${{s.id}}','${{esc(defaultLane || 'NOW')}}')">
      <div>
        <div class=mp-title>${{esc(s.summary)}}</div>
        <div class=mp-meta>${{linked?'已加入':'未加入'}} · ${{esc(pri)}} · ${{esc(lane)}} · ${{esc(s.cat)}} · ${{daysAgo(s.updated_iso)}} · ${{s.turns}}轮</div>
        <div class=mp-ask>${{esc(s.ask || '(无首问)')}}</div>
      </div>
    </label>`;
  }}).join('');
}}
function openMissionPicker(e, defaultLane){{
  e.stopPropagation();
  const m = document.getElementById('modal'), inner = document.getElementById('modalInner');
  inner.classList.add('mission-picker');
  inner.innerHTML = `
    <div class=m-head style="--c:#9FE870">
      <h2>+ Mission · 勾选已有任务</h2>
      <div class=meta><span>从主看板现有 session / 合并任务中选择</span><span>勾选=加入 Mission，取消=移除 Mission</span></div>
    </div>
    <div class=m-body>
      <div class=mp-tools>
        <input id=mpSearch placeholder="搜索任务 / 客户 / skill / 关键词" autocomplete=off>
        <button class="btn primary" onclick="newMission(event,'${{esc(defaultLane || 'NOW')}}')">手动新建</button>
      </div>
      <div class=mp-list id=mpList>${{missionPickerRows(defaultLane || 'NOW')}}</div>
    </div>
    <div class=m-foot>
      <button class=btn onclick="closeModal()">完成</button>
      <div style="flex:1"></div>
      <button class=btn onclick="loadMissions()">刷新 Mission</button>
    </div>`;
  m.classList.add('show');
  const q = document.getElementById('mpSearch');
  q.addEventListener('input', ev => {{
    document.getElementById('mpList').innerHTML = missionPickerRows(defaultLane || 'NOW', ev.target.value);
  }});
}}
async function toggleSessionMission(e, sid, defaultLane){{
  e.stopPropagation();
  const checked = e.currentTarget.checked;
  const s = DATA.find(x => x.id === sid); if(!s) return;
  const linked = linkedMissionForSession(sid);
  if(checked){{
    const lane = defaultLane || (linked && linked.lane) || 'NOW';
    const payload = {{
      id: linked ? linked.id : missionIdForSession(sid),
      title: s.summary,
      lane,
      priority: linked ? linked.priority : 'P1',
      type: 'project',
      cadence: linked ? linked.cadence : '',
      next: s.ask || '继续推进这个任务',
      query: (s.summary + ' ' + (s.ask||'')).slice(0, 160),
      session_id: sid,
    }};
    try{{ await saveMission(payload); toast('已加入 Mission','ok'); }}
    catch(err){{ e.currentTarget.checked=false; toast('加入失败','err'); }}
  }} else {{
    if(!linked) return;
    const r = await fetch('/missions/delete', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{id: linked.id}})}});
    if(r.ok){{ await loadMissions(); toast('已从 Mission 移除','ok'); }}
    else{{ e.currentTarget.checked=true; toast('移除失败','err'); }}
  }}
  const search = document.getElementById('mpSearch');
  const list = document.getElementById('mpList');
  if(search && list) list.innerHTML = missionPickerRows(defaultLane || 'NOW', search.value);
}}
let _mpDrag = null;
function mpGrab(e){{
  if(e.button !== 0 || e.target.tagName === 'BUTTON') return;
  const panel = e.currentTarget.closest('.mission-panel');
  if(!panel) return;
  panel.classList.add('dragging-self');
  panel.style.zIndex = 90;
  _mpDrag = {{panel, lane:panel.dataset.lane, sx:e.clientX, sy:e.clientY, ox:panel.offsetLeft, oy:panel.offsetTop}};
  document.addEventListener('mousemove', mpMove);
  document.addEventListener('mouseup', mpDrop, {{once:true}});
  e.preventDefault();
}}
function mpMove(e){{
  if(!_mpDrag) return;
  const p = _mpDrag.panel;
  const nx = Math.max(8, Math.min(innerWidth - p.offsetWidth - 8, _mpDrag.ox + e.clientX - _mpDrag.sx));
  const ny = Math.max(0, Math.min(innerHeight - 110, _mpDrag.oy + e.clientY - _mpDrag.sy));
  p.style.left = nx+'px'; p.style.top = ny+'px';
}}
function mpDrop(){{
  if(!_mpDrag) return;
  document.removeEventListener('mousemove', mpMove);
  _mpDrag.panel.classList.remove('dragging-self');
  _mpDrag.panel.style.zIndex = '';
  if(_mpDrag.lane){{
    const layout = loadMissionLayout();
    layout[_mpDrag.lane] = {{x:_mpDrag.panel.offsetLeft, y:_mpDrag.panel.offsetTop}};
    saveMissionLayout(layout);
  }}
  _mpDrag = null;
}}
let MISSION_DRAG_ID = null;
function mtStart(e, id){{
  MISSION_DRAG_ID = id;
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('text/plain', id);
  e.currentTarget.classList.add('dragging');
  e.stopPropagation();
}}
function mtEnd(e){{
  document.querySelectorAll('.mission-card.dragging,.mission-panel.drop-here').forEach(x=>x.classList.remove('dragging','drop-here'));
  MISSION_DRAG_ID = null;
}}
function laneDragOver(e){{
  if(!MISSION_DRAG_ID) return;
  e.preventDefault(); e.stopPropagation();
  e.currentTarget.classList.add('drop-here');
}}
function laneDragLeave(e){{
  if(e.currentTarget.contains(e.relatedTarget)) return;
  e.currentTarget.classList.remove('drop-here');
}}
async function laneDrop(e){{
  if(!MISSION_DRAG_ID) return;
  e.preventDefault(); e.stopPropagation();
  const panel = e.currentTarget;
  panel.classList.remove('drop-here');
  const lane = panel.dataset.lane;
  const m = MISSIONS.find(x => x.id === MISSION_DRAG_ID);
  if(!m || !lane || m.lane === lane) return;
  try{{
    await saveMission({{...m, lane}});
    toast(`已移到 ${{lane}}`,'ok');
  }}catch(err){{ toast('移动失败','err'); }}
}}
document.getElementById('btnMission').addEventListener('click', e=>{{
  e.stopPropagation();
  document.getElementById('missionLayer').classList.toggle('hidden');
}});

let _mqAc=null;
function missionTone(){{
  try{{
    _mqAc = _mqAc || new (window.AudioContext||window.webkitAudioContext)();
    [523,659,784,1046].forEach((f,i)=>{{
      const t=_mqAc.currentTime+i*.07, o=_mqAc.createOscillator(), g=_mqAc.createGain();
      o.type='triangle'; o.frequency.value=f; g.gain.setValueAtTime(.0001,t); g.gain.exponentialRampToValueAtTime(.13,t+.01); g.gain.exponentialRampToValueAtTime(.0001,t+.18);
      o.connect(g); g.connect(_mqAc.destination); o.start(t); o.stop(t+.2);
    }});
  }}catch(e){{}}
}}
function missionSpark(rect){{
  missionTone();
  const c=document.getElementById('missionFx'), ctx=c.getContext('2d'), r=devicePixelRatio||1;
  c.width=innerWidth*r; c.height=innerHeight*r; c.style.width=innerWidth+'px'; c.style.height=innerHeight+'px'; ctx.setTransform(r,0,0,r,0,0);
  const x=rect?rect.left+rect.width/2:innerWidth-180, y=rect?rect.top+rect.height/2:140;
  const colors=['#9FE870','#FFD17A','#22d3a8','#f472b6','#ffffff'];
  const parts=Array.from({{length:54}},()=>{{const a=-Math.PI/2+(Math.random()-.5)*Math.PI*1.3, v=4+Math.random()*6; return {{x,y,vx:Math.cos(a)*v,vy:Math.sin(a)*v,g:.18,s:4+Math.random()*6,life:54+Math.random()*30,c:colors[(Math.random()*colors.length)|0],rot:Math.random()*6,vr:(Math.random()-.5)*.28}}}});
  function loop(){{
    ctx.clearRect(0,0,innerWidth,innerHeight);
    for(const p of parts){{p.life--;p.vy+=p.g;p.x+=p.vx;p.y+=p.vy;p.rot+=p.vr;ctx.save();ctx.globalAlpha=Math.max(0,Math.min(1,p.life/28));ctx.translate(p.x,p.y);ctx.rotate(p.rot);ctx.fillStyle=p.c;ctx.fillRect(-p.s/2,-p.s/3,p.s,p.s*.55);ctx.restore();}}
    if(parts.some(p=>p.life>0)) requestAnimationFrame(loop); else ctx.clearRect(0,0,innerWidth,innerHeight);
  }}
  loop();
}}

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
function isStale(iso){{ return (Date.now()-new Date(iso).getTime())/86400000 > 60; }}
function missionMatchesSession(m, s){{
  if(!m || !s) return false;
  if(m.session_id && m.session_id === s.id) return true;
  const hay = (s.summary+' '+s.ask+' '+s.cat+' '+(s.body||'')).toLowerCase();
  const raw = (m.query || m.title || '').toLowerCase().split(/\\s+/).filter(x => x.length >= 2);
  if(!raw.length) return false;
  let hits = 0;
  for(const t of raw){{ if(hay.includes(t)) hits++; }}
  return hits >= Math.min(2, raw.length);
}}
function missionForSession(s){{
  const active = missionActive().filter(m => missionMatchesSession(m, s)).sort((a,b) => (PRI_RANK[a.priority]??9)-(PRI_RANK[b.priority]??9));
  return active[0] || null;
}}

// ── Filtering ──
function filtered(){{
  let arr = DATA.slice();
  if(state.q){{
    const gs = expandTokens(state.q);
    arr = arr.filter(s => matchQ(s.summary+' '+s.ask+' '+s.cat+' '+(s.body||''), gs));
  }}
  // Hide group members (only show primaries)
  arr = arr.filter(s => !s.group_id || s.is_primary);
  arr.sort((a,b) => {{
    const ma=missionForSession(a), mb=missionForSession(b);
    if(!!ma !== !!mb) return mb ? 1 : -1;
    if(ma && mb && ma.priority !== mb.priority) return (PRI_RANK[ma.priority]??9)-(PRI_RANK[mb.priority]??9);
    const pa=PINS.has(a.id), pb=PINS.has(b.id);
    if(pa!==pb) return pb-pa;
    return new Date(b.updated_iso)-new Date(a.updated_iso);
  }});
  if(SELECTED_MISSION_ID){{
    const m = MISSIONS.find(x => x.id === SELECTED_MISSION_ID);
    if(m) arr = arr.filter(s => missionMatchesSession(m, s));
  }}
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
function cardHTML(s, forcedMission){{
  const snip = snippet(s, state.q);
  const fresh = isFresh(s.updated_iso);
  const pinned = PINS.has(s.id);
  const stale = isStale(s.updated_iso) && !pinned;
  const isGroup = s.is_primary && s.group_size > 1;
  const groupTitle = isGroup ? (s.group_name || s.summary) : s.summary;
  const mission = forcedMission || missionForSession(s);
  const missionColor = mission ? (PRI_COLOR[mission.priority] || '#9FE870') : '';
  let membersHTML = '';
  if(isGroup){{
    const ms = DATA.filter(x => x.group_id === s.group_id && x.id !== s.id);
    membersHTML = `<div class=group-members>${{ms.map(m => `
      <div class=group-member title="${{esc(m.summary)}}">
        <span class=name onclick="event.stopPropagation();openModal('${{m.id}}')">↳ ${{esc(m.summary)}}</span>
        <span class=meta style="font-size:10.5px;color:var(--text-m);white-space:nowrap">${{m.turns}}轮·${{daysAgo(m.updated_iso)}}</span>
        <span class=pop title="从合并中移出" onclick="event.stopPropagation();unmerge('${{m.id}}')">✕</span>
      </div>`).join('')}}</div>`;
  }}
  return `<article class="card ${{isGroup?'group':''}} ${{pinned?'pinned':''}} ${{stale?'stale':''}}" style="--c:${{s.color}}" draggable=true data-id="${{s.id}}"
    ondragstart="cdStart(event,'${{s.id}}')" ondragend="cdEnd(event)"
    ondragover="cdOver(event,'${{s.id}}')" ondragleave="cdLeave(event)" ondrop="cdDrop(event,'${{s.id}}')"
    onclick="openModal('${{s.id}}')">
    ${{mission?`<div class=mission-badge style="--p:${{missionColor}}">${{mission.priority}} · ${{esc(mission.lane)}} · ${{esc(mission.title)}}</div>`:''}}
    ${{isGroup?`<div class=group-badge>🧩 合并任务 · ${{s.group_size}} 个会话</div>`:''}}
    <div class=card-head><h3>${{highlight(groupTitle, state.q)}}</h3></div>
    <div class=meta>
      <span class="ago ${{fresh?'fresh':''}}">${{daysAgo(s.updated_iso)}}</span>
      <span class=sep>·</span><span>🔁 ${{s.turns}} 轮</span>
      <span class=sep>·</span><span>${{s.date}}</span>
    </div>
    ${{membersHTML}}
    ${{snip}}
    <div class=ask>${{s.ask?highlight(s.ask,state.q):'<span class=empty></span>'}}</div>
    <footer onclick="event.stopPropagation()">
      ${{mission?`<button class="btn done" onclick="completeMissionSession(event,'${{esc(mission.id)}}','${{s.id}}')">✓ Done</button>`:''}}
      <button class="btn primary" onclick="resume('${{s.id}}')">▶ 继续</button>
      <button class="btn icon" onclick="togglePin('${{s.id}}')" title="固定">${{pinned?'📍':'📌'}}</button>
      <button class="btn icon" onclick="renameIt('${{s.id}}')" title="重命名">✎</button>
      <button class="btn icon" onclick="showCatPicker(event,'${{s.id}}')" title="移到分类">📁</button>
      <span style="flex:1"></span>
      <button class="btn icon danger" onclick="del_('${{s.id}}')" title="删除">🗑</button>
    </footer>
  </article>`;
}}
function togglePanelItems(e, cat){{
  e.stopPropagation();
  if(PANEL_EXPANDED.has(cat)) PANEL_EXPANDED.delete(cat); else PANEL_EXPANDED.add(cat);
  localStorage.setItem(PANEL_EXPANDED_KEY, JSON.stringify([...PANEL_EXPANDED]));
  render();
}}

function render(){{
  document.getElementById('metaCount').textContent = `${{missionActive().length}} Mission · ${{TOTAL}} 段记忆`;
  document.getElementById('world').innerHTML = '';
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

async function unmerge(sid){{
  if(!confirm('从合并中移出？')) return;
  const r = await fetch('/groups/unmerge', {{method:'POST',
    headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{id: sid}})}});
  if(r.ok){{ toast('已拆分 ✓','ok'); setTimeout(()=>location.reload(), 350); }}
  else toast('拆分失败','err');
}}

async function renameIt(id){{
  const s = DATA.find(x=>x.id===id); if(!s) return;
  const name = prompt('重命名会话：', s.summary);
  if(!name || name===s.summary) return;
  const r = await fetch('/rename?id='+id,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{name}})}});
  if(r.ok){{ s.summary=name; toast('已重命名','ok'); render(); closeModal(); }}
  else toast('重命名失败','err');
}}

function showCatPicker(e, sid){{
  e.stopPropagation();
  document.querySelectorAll('.cat-picker').forEach(x => x.remove());
  const s = DATA.find(x => x.id === sid); if(!s) return;
  const rect = e.currentTarget.getBoundingClientRect();
  const menu = document.createElement('div');
  menu.className = 'cat-picker';
  menu.innerHTML = '<div class=cp-title>移动到分类</div>' + CAT_ORDER.map(c =>
    `<button class="cp-item ${{c===s.cat?'cur':''}}" data-cat="${{esc(c)}}" style="--c:${{CAT_COLOR[c]}}">
       <span class=dot></span>${{esc(c)}}${{c===s.cat?' <span class=tag>当前</span>':''}}
     </button>`).join('');
  Object.assign(menu.style, {{
    position:'fixed', left: Math.max(8, rect.left - 80) + 'px',
    top: (rect.bottom + 6) + 'px', zIndex: 200
  }});
  document.body.appendChild(menu);
  const mr = menu.getBoundingClientRect();
  if(mr.bottom > window.innerHeight - 8) menu.style.top = Math.max(8, rect.top - mr.height - 6) + 'px';
  if(mr.right > window.innerWidth - 8) menu.style.left = (window.innerWidth - mr.width - 12) + 'px';
  menu.addEventListener('click', async ev => {{
    const btn = ev.target.closest('.cp-item'); if(!btn) return;
    ev.stopPropagation();
    const cat = btn.dataset.cat;
    if(cat === s.cat){{ menu.remove(); return; }}
    const r = await fetch('/sessions/recat', {{method:'POST',
      headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{id: sid, cat}})}});
    menu.remove();
    if(r.ok){{ toast(`已移到「${{cat}}」 ✓`,'ok'); setTimeout(()=>location.reload(), 350); }}
    else toast('移动失败','err');
  }});
  setTimeout(() => {{
    document.addEventListener('click', function close(e2){{
      if(!menu.contains(e2.target)){{ menu.remove(); document.removeEventListener('click', close); }}
    }});
  }}, 0);
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
      ${{d.resume_block_reason?`<section><h3>⚠ 恢复保护</h3><div class=purpose style="border-color:rgba(245,158,11,.45);background:rgba(245,158,11,.12);color:#fbbf24">${{esc(d.resume_block_reason)}}</div></section>`:''}}
      <section><h3>🔗 链路 · ${{d.chain.length}} 轮</h3>
        ${{d.chain.map(c=>`<div style="padding:7px 0;border-bottom:1px solid var(--line);font-size:12px"><b style="color:var(--text)">#${{c.i}}</b> <span style="opacity:.85">${{esc(c.user.slice(0,160))}}</span>${{c.repeat_count>1?` <span style="color:#fbbf24">(已折叠 ${{c.repeat_count}} 次重复)</span>`:''}}${{c.has_reply?'':' <span style="color:var(--danger)">(无回复)</span>'}}</div>`).join('')}}
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
function closeModal(){{ document.getElementById('modal').classList.remove('show'); document.getElementById('modalInner').classList.remove('mission-picker'); }}
document.getElementById('modal').addEventListener('click', e=>{{ if(e.target.id==='modal') closeModal(); }});

async function resume(id){{ const r = await fetch('/resume?id='+id,{{method:'POST'}}); const msg = r.ok ? '已新开窗口' : (await r.text() || '失败'); toast(msg,r.ok?'ok':'err'); }}
function togglePin(id){{
  if(PINS.has(id)){{ PINS.delete(id); toast('已取消固定','ok'); }}
  else{{ PINS.add(id); toast('已固定到顶部','ok'); }}
  localStorage.setItem('pins', JSON.stringify([...PINS]));
  render();
}}
async function del_(id){{ if(!confirm('删除？此操作不可逆')) return; const r = await fetch('/delete?id='+id,{{method:'POST'}}); if(r.ok){{ closeModal(); toast('已删除','ok'); setTimeout(()=>location.reload(),350); }} }}

// ── Toast ──
function toast(msg, kind){{ const t = document.getElementById('toast'); t.textContent = msg; t.className = (kind||'')+' show'; setTimeout(()=>t.classList.remove('show'),1800); }}

// ── Keyboard ──
document.addEventListener('keydown', e=>{{
  if(e.target.tagName==='INPUT') {{
    if(e.key==='Escape') e.target.blur();
    return;
  }}
  if(e.key==='Escape') closeModal();
  if(e.key==='r' || e.key==='R'){{ if(confirm('重置作战空间布局？')) {{ localStorage.removeItem(MQ_LAYOUT_KEY); localStorage.removeItem(LAYOUT_KEY); location.reload(); }} }}
}});

// ── Search ──
const qEl = document.getElementById('q');
if(qEl) qEl.addEventListener('input', e=>{{ state.q = e.target.value; renderMissions(); render(); }});

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
loadMissions();
render();
</script></body></html>"""
