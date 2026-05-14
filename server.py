"""Copilot 对话看板 · 本地服务
运行: python server.py  → 浏览器访问 http://localhost:8765
"""
import sqlite3, os, re, html, json, shutil, subprocess, webbrowser, sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from datetime import datetime

HOME = Path(os.environ['USERPROFILE'])
DB = HOME / '.copilot' / 'session-store.db'
STATE_DIR = HOME / '.copilot' / 'session-state'
PORT = 8765

CATS = [
    ('🧠 技能 / 数字分身', ['skill', 'openclaw', '分身', 'wechat']),
    ('💼 客户 & 商务', ['ptu', 'datazone', 'claude', 'gpt', 'justification', 'tpm', 'bedrock']),
    ('📊 汇报 & 沟通', ['老板', '汇报', 'summary', 'business']),
    ('📚 学习 & 成长', ['english', '英语', '学习', 'learning', 'plan', '成长']),
    ('🛠️ 工具 & 自助', ['email', '窗口', 'visualize', 'history', 'coding', 'dashboard', '看板']),
]

def categorize(summary, ask):
    t = ((summary or '') + ' ' + (ask or '')).lower()
    for name, kws in CATS:
        if any(k in t for k in kws):
            return name
    return '📦 其他'

# Known noisy prompt-template prefixes that pollute summary
_BAD_SUMMARY_PATTERNS = (
    'extract memorable facts',
    'here is the conversation',
    'a scheduled automation',
    '[a scheduled automation',
    'present these results to the user',
    'summarize the following conversation',
    "user:",
    "assistant:",
)

def clean_summary(raw, ask=''):
    """Sanitize polluted summaries: long prompt-template dumps from background agents."""
    s = (raw or '').strip()
    if not s:
        return (ask or '(未命名)')[:80]
    low = s.lower()
    is_bad = (len(s) > 140 and any(p in low for p in _BAD_SUMMARY_PATTERNS)) \
             or any(low.startswith(p) for p in _BAD_SUMMARY_PATTERNS)
    if is_bad:
        # Try first sentence of ask, else first 60 chars of summary stripped
        clean = (ask or '').strip().split('\n')[0][:80]
        if not clean:
            clean = re.sub(r'\s+', ' ', s)[:80]
        return '⚠ ' + clean + ('…' if len(clean) >= 80 else '')
    return s[:120] + ('…' if len(s) > 120 else '')

def fetch_sessions():
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute("""
      SELECT s.id, s.summary, s.created_at, s.updated_at, s.cwd,
        (SELECT COUNT(*) FROM turns WHERE session_id=s.id) turns,
        (SELECT user_message FROM turns WHERE session_id=s.id AND user_message IS NOT NULL ORDER BY turn_index LIMIT 1) ask
      FROM sessions s
      WHERE LOWER(COALESCE(s.cwd,'')) NOT LIKE '%clawpilot%'
      ORDER BY COALESCE(s.updated_at, s.created_at) DESC
    """).fetchall()
    # Build a haystack of all user messages per session for full-text search
    body_rows = con.execute("""
      SELECT session_id,
        GROUP_CONCAT(SUBSTR(COALESCE(user_message,''), 1, 600)
                  || ' ' || SUBSTR(COALESCE(assistant_response,''), 1, 400), ' ') body
      FROM turns GROUP BY session_id
    """).fetchall()
    bodies = {r['session_id']: (r['body'] or '') for r in body_rows}
    con.close()
    groups = load_groups()
    overrides = load_overrides()
    sid_to_group = {}
    for gid, info in groups.items():
        for m in info.get('members', []):
            sid_to_group[m] = (gid, info)
    out = []
    for r in rows:
        ask = (r['ask'] or '').strip().replace('\n', ' ')
        gid_info = sid_to_group.get(r['id'])
        gid = gid_info[0] if gid_info else None
        ginfo = gid_info[1] if gid_info else None
        is_primary = bool(ginfo and ginfo.get('primary') == r['id'])
        # Strip skill-context blocks + collapse whitespace, cap to 4000 chars
        body = re.sub(r'<skill-context.*?</skill-context>', '', bodies.get(r['id'], ''), flags=re.S)
        body = re.sub(r'\s+', ' ', body).strip()[:8000]
        out.append(dict(id=r['id'], summary=clean_summary(r['summary'], ask),
                        raw_summary=r['summary'] or '',
                        date=r['created_at'][:10],
                        updated=(r['updated_at'] or r['created_at'])[:10],
                        updated_iso=(r['updated_at'] or r['created_at']),
                        turns=r['turns'],
                        ask=ask[:240],
                        body=body,
                        cat=overrides.get(r['id']) or categorize(r['summary'], r['ask']),
                        group_id=gid,
                        is_primary=is_primary,
                        group_name=(ginfo or {}).get('name', '') if ginfo else '',
                        group_size=len(ginfo['members']) if ginfo else 0))
    return out

def delete_session(sid):
    """从 DB 和 session-state 文件夹彻底删除"""
    con = sqlite3.connect(DB, timeout=10)
    try:
        cur = con.cursor()
        for tbl in ('turns', 'checkpoints', 'session_files', 'session_refs'):
            cur.execute(f"DELETE FROM {tbl} WHERE session_id=?", (sid,))
        try:
            cur.execute("DELETE FROM search_index WHERE session_id=?", (sid,))
        except sqlite3.OperationalError:
            pass
        cur.execute("DELETE FROM sessions WHERE id=?", (sid,))
        con.commit()
    finally:
        con.close()
    folder = STATE_DIR / sid
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)

def rename_session(sid, new_name):
    con = sqlite3.connect(DB, timeout=10)
    try:
        con.execute("UPDATE sessions SET summary=? WHERE id=?", (new_name[:120], sid))
        con.commit()
    finally:
        con.close()

# ─── Group storage (merge duplicates into one task) ────────────────────────
GROUPS_FILE = HOME / '.copilot' / 'session-groups.json'

def load_groups():
    if GROUPS_FILE.exists():
        try: return json.loads(GROUPS_FILE.read_text(encoding='utf-8'))
        except Exception: return {}
    return {}

def save_groups(g):
    GROUPS_FILE.parent.mkdir(parents=True, exist_ok=True)
    GROUPS_FILE.write_text(json.dumps(g, ensure_ascii=False, indent=2), encoding='utf-8')

def _find_group(g, sid):
    for gid, info in g.items():
        if sid in info.get('members', []):
            return gid
    return None

def merge_sessions(primary, secondary):
    """Add `secondary` into the group of `primary`. Creates group if needed.
       If `secondary` already belongs to another group, that group merges in."""
    if primary == secondary: return None
    g = load_groups()
    pgid = _find_group(g, primary)
    if pgid is None:
        pgid = primary
        g[pgid] = {'name': '', 'primary': primary, 'members': [primary]}
    sgid = _find_group(g, secondary)
    if sgid and sgid != pgid:
        for m in g[sgid]['members']:
            if m not in g[pgid]['members']:
                g[pgid]['members'].append(m)
        del g[sgid]
    elif sgid is None:
        g[pgid]['members'].append(secondary)
    save_groups(g)
    return pgid

def unmerge_session(sid):
    g = load_groups()
    gid = _find_group(g, sid)
    if not gid: return False
    info = g[gid]
    info['members'].remove(sid)
    if info.get('primary') == sid:
        info['primary'] = info['members'][0] if info['members'] else None
    if len(info['members']) <= 1:
        del g[gid]
    save_groups(g)
    return True

def rename_group(gid, name):
    g = load_groups()
    if gid in g:
        g[gid]['name'] = name[:120]
        save_groups(g)
        return True
    return False

# ─── Per-session category override ─────────────────────────────────────────
OVERRIDES_FILE = HOME / '.copilot' / 'session-overrides.json'

def load_overrides():
    if OVERRIDES_FILE.exists():
        try: return json.loads(OVERRIDES_FILE.read_text(encoding='utf-8'))
        except Exception: return {}
    return {}

def save_overrides(d):
    OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
    OVERRIDES_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')

def set_session_cat(sid, cat):
    d = load_overrides()
    if cat:
        d[sid] = cat
    else:
        d.pop(sid, None)
    save_overrides(d)

def session_detail(sid):
    """Return structured PRD-like summary of one session."""
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    s = con.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if not s:
        con.close(); return None
    turns = con.execute("""SELECT turn_index, user_message, assistant_response, timestamp
                           FROM turns WHERE session_id=? ORDER BY turn_index""", (sid,)).fetchall()
    con.close()

    # Build chain (turn-by-turn) with light cleanup
    chain = []
    for t in turns:
        u = (t['user_message'] or '').strip()
        a = (t['assistant_response'] or '').strip()
        # Strip skill-context blocks for readability
        u = re.sub(r'<skill-context.*?</skill-context>', '', u, flags=re.S).strip()
        chain.append({
            'i': t['turn_index'],
            'time': t['timestamp'],
            'user': u[:300],
            'user_full_len': len(t['user_message'] or ''),
            'has_reply': bool(a),
            'reply_preview': a[:240],
            'reply_len': len(a),
        })

    # Scan session-state folder for artifacts
    folder = STATE_DIR / sid
    artifacts = []
    if folder.exists():
        for p in folder.rglob('*'):
            if p.is_file() and p.name not in ('events.jsonl', 'session.db', 'workspace.yaml') and not p.name.startswith('inuse.'):
                rel = p.relative_to(folder).as_posix()
                artifacts.append({
                    'path': rel,
                    'abs': str(p),
                    'size': p.stat().st_size,
                    'mtime': datetime.fromtimestamp(p.stat().st_mtime).strftime('%Y-%m-%d %H:%M'),
                    'kind': 'plan' if p.name == 'plan.md' else ('doc' if p.suffix in ('.md','.txt') else ('data' if p.suffix in ('.csv','.json','.yaml') else 'other'))
                })
    artifacts.sort(key=lambda x: (0 if x['kind']=='plan' else 1, x['path']))

    # Read plan.md head if present
    plan_preview = None
    plan = folder / 'plan.md'
    if plan.exists():
        try:
            plan_preview = plan.read_text(encoding='utf-8', errors='replace')[:1500]
        except Exception:
            pass

    # Determine status
    last = chain[-1] if chain else None
    if not chain:
        status = ('empty', '空会话')
    elif last and not last['has_reply']:
        status = ('interrupted', '最后一轮无回复（可能中断）')
    else:
        status = ('ok', '正常')

    # Detect key themes from user messages (simple keyword scan)
    all_user = ' '.join(c['user'] for c in chain).lower()
    themes = []
    theme_map = {
        '英语/学习': ['英语','english','学习','learn','plan'],
        '客户/商务': ['客户','商务','business','客户名','justification','报价','quote','ptu','datazone'],
        '部署/工具': ['部署','deploy','wechat','openclaw','skill','安装','setup'],
        '汇报/沟通': ['汇报','老板','summary','报告','briefing'],
        '看板/对话管理': ['看板','dashboard','对话','session','历史','history'],
        '模型/AI': ['模型','model','claude','gpt','copilot','agent'],
    }
    for name, kws in theme_map.items():
        if any(k in all_user for k in kws):
            themes.append(name)

    return {
        'id': s['id'],
        'summary': s['summary'] or '(未命名)',
        'cwd': s['cwd'],
        'created_at': s['created_at'],
        'updated_at': s['updated_at'] or s['created_at'],
        'turns': len(chain),
        'first_ask': chain[0]['user'] if chain else '',
        'last_ask': chain[-1]['user'] if chain else '',
        'cat': categorize(s['summary'], chain[0]['user'] if chain else ''),
        'cat_color': CAT_COLORS.get(categorize(s['summary'], chain[0]['user'] if chain else ''), '#a0aec0'),
        'chain': chain,
        'artifacts': artifacts,
        'plan_preview': plan_preview,
        'status': status[0],
        'status_label': status[1],
        'themes': themes,
        'duration_days': max(1, (datetime.fromisoformat(s['created_at'].replace('Z','+00:00')).date()
                                 .toordinal() - datetime.fromisoformat((s['updated_at'] or s['created_at']).replace('Z','+00:00')).date().toordinal()) * -1) if s['updated_at'] else 0,
    }

def resume_session(sid):
    """新开一个 Windows Terminal/cmd 窗口运行 copilot --resume"""
    # Try Windows Terminal first, fallback to cmd
    try:
        subprocess.Popen(['wt.exe', '-w', '0', 'nt', 'cmd', '/k',
                          f'copilot --resume={sid}'], shell=False)
        return True
    except FileNotFoundError:
        subprocess.Popen(f'start cmd /k copilot --resume={sid}', shell=True)
        return True

# Category color coding (semantic, ADHD-friendly consistent across UI)
CAT_COLORS = {
    '🧠 技能 / 数字分身': '#a78bfa',
    '💼 客户 & 商务': '#fb923c',
    '📊 汇报 & 沟通': '#22d3a8',
    '📚 学习 & 成长': '#f472b6',
    '🛠️ 工具 & 自助': '#38bdf8',
    '📦 其他': '#94a3b8',
}

def render():
    sessions = fetch_sessions()  # already sorted by recency desc
    total = len(sessions)
    # Pre-serialize for client
    for s in sessions:
        s['color'] = CAT_COLORS.get(s['cat'], '#a0aec0')
    data_json = json.dumps(sessions, ensure_ascii=False)
    cats = list(CAT_COLORS.keys())
    cat_color_json = json.dumps(CAT_COLORS, ensure_ascii=False)
    cat_order_json = json.dumps(cats, ensure_ascii=False)
    cat_icon_json = json.dumps({c: c.split(' ', 1)[0] for c in cats}, ensure_ascii=False)
    chip_html = ''.join(
        f'<button class="chip" data-cat="{c}" style="--c:{CAT_COLORS[c]}"><span class="dot"></span>{c}</button>'
        for c in cats)
    return f"""<!doctype html><html lang=zh><head><meta charset=utf-8>
<title>Memory · Copilot 对话宫殿</title>
<style>
:root{{
  --bg:#17120f; --bg2:#211814; --surface:#2a1f1a;
  --border:rgba(255,220,190,.12); --border-h:rgba(255,220,190,.35);
  --text:#f5ebe0; --text-d:#c9b8a8; --text-m:#8a7a6d;
  --accent:#e8a478; --danger:#e87a6a; --ok:#9ed0b8;
  --radius:14px; --shadow:0 4px 20px rgba(0,0,0,.3);
}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{height:100%;background:var(--bg);color:var(--text);font-family:-apple-system,'Inter','Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}}
body{{
  background:
    radial-gradient(ellipse 60% 40% at 85% -5%, rgba(232,164,120,.15) 0%, transparent 60%),
    radial-gradient(ellipse 50% 40% at 10% 100%, rgba(182,148,244,.08) 0%, transparent 60%),
    var(--bg);
  background-attachment:fixed;
}}
button{{font-family:inherit;font-size:inherit;color:inherit;background:none;border:none;cursor:pointer}}
@media (prefers-reduced-motion: reduce){{*{{animation-duration:.01s!important;transition-duration:.01s!important}}}}

/* Layout */
.app{{max-width:1360px;margin:0 auto;padding:32px 32px 80px}}
.topbar{{display:flex;align-items:baseline;gap:18px;margin-bottom:6px}}
.topbar h1{{font-size:22px;font-weight:600;letter-spacing:-.3px}}
.topbar .meta{{color:var(--text-m);font-size:13px}}
.hint{{color:var(--text-m);font-size:12px;margin-bottom:20px}}
.hint kbd{{background:var(--surface);border:1px solid var(--border);border-radius:4px;padding:1px 6px;font-size:11px;font-family:inherit;color:var(--text-d)}}

/* Search & controls */
.controls{{position:sticky;top:0;background:linear-gradient(180deg,var(--bg) 80%,transparent);z-index:20;padding:8px 0 16px;margin:0 -32px 20px;padding-left:32px;padding-right:32px}}
.search-row{{display:flex;gap:10px;align-items:center;margin-bottom:12px}}
.search{{flex:1;display:flex;align-items:center;gap:10px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:10px 14px;transition:border-color .2s}}
.search:focus-within{{border-color:var(--accent)}}
.search svg{{opacity:.5;flex-shrink:0}}
.search input{{flex:1;background:none;border:none;outline:none;color:var(--text);font-size:14px;font-family:inherit}}
.search .kbd{{color:var(--text-m);font-size:11px;background:rgba(255,255,255,.04);border:1px solid var(--border);border-radius:4px;padding:2px 6px}}
.search input:focus ~ .kbd{{display:none}}
.sort{{display:flex;gap:4px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:4px}}
.sort button{{padding:6px 12px;border-radius:10px;font-size:12px;color:var(--text-m);transition:.15s;letter-spacing:.3px}}
.sort button.active{{background:rgba(232,164,120,.15);color:var(--accent)}}
.sort button:hover:not(.active){{color:var(--text-d)}}
.chips{{display:flex;gap:8px;flex-wrap:wrap}}
.chip{{display:inline-flex;align-items:center;gap:8px;padding:6px 12px;border-radius:100px;background:var(--surface);border:1px solid var(--border);font-size:12px;color:var(--text-d);transition:.2s;letter-spacing:.3px}}
.chip .dot{{width:7px;height:7px;border-radius:50%;background:var(--c);display:inline-block}}
.chip:hover{{border-color:var(--c);color:var(--text)}}
.chip.active{{background:color-mix(in srgb, var(--c) 18%, transparent);border-color:var(--c);color:var(--text)}}
.chip.all{{--c:var(--accent)}}
.chip.pinned{{--c:#ffd37a}}

/* Stats strip */
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}}
.stat{{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:14px 16px}}
.stat .n{{font-size:24px;font-weight:600;color:var(--text);letter-spacing:-.5px}}
.stat .l{{font-size:11px;color:var(--text-m);letter-spacing:1px;text-transform:uppercase;margin-top:2px}}

/* Kanban columns — bold, distinct, ADHD-friendly */
.kanban{{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:18px;align-items:start}}
.col{{
  background:linear-gradient(180deg,
    color-mix(in srgb, var(--c) 22%, var(--bg2)) 0%,
    color-mix(in srgb, var(--c) 7%, var(--bg2)) 100%);
  border:1px solid color-mix(in srgb, var(--c) 32%, var(--border));
  border-radius:18px;padding:14px;min-height:120px;
  box-shadow:0 1px 0 rgba(255,255,255,.04) inset, 0 8px 30px rgba(0,0,0,.18);
  transition:.2s;
}}
.col.drop-here{{border-color:var(--c);box-shadow:0 0 0 2px color-mix(in srgb, var(--c) 50%, transparent), 0 8px 30px rgba(0,0,0,.25)}}
.col-head{{display:flex;align-items:center;gap:10px;padding:6px 6px 12px;border-bottom:1px solid color-mix(in srgb, var(--c) 28%, transparent);margin-bottom:12px}}
.col-head .ic{{font-size:18px}}
.col-head .title{{flex:1;color:#fff;font-weight:600;letter-spacing:.2px;text-shadow:0 1px 0 rgba(0,0,0,.25);font-size:14px}}
.col-head .count{{background:color-mix(in srgb, var(--c) 28%, transparent);color:#fff;padding:2px 10px;border-radius:100px;font-size:11px;font-weight:700;letter-spacing:.5px;border:1px solid color-mix(in srgb, var(--c) 50%, transparent)}}
.col-empty{{font-size:11.5px;color:rgba(255,255,255,.45);font-style:italic;text-align:center;padding:18px 8px}}

/* Cards */
.card{{position:relative;background:color-mix(in srgb, var(--c) 8%, var(--surface));border:1px solid color-mix(in srgb, var(--c) 22%, var(--border));border-radius:14px;padding:14px;cursor:pointer;transition:transform .2s cubic-bezier(.2,.8,.2,1), border-color .2s, box-shadow .2s, opacity .2s;overflow:hidden;margin-bottom:10px}}
.card::before{{content:'';position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--c)}}
.card:hover{{border-color:var(--c);transform:translateY(-2px);box-shadow:0 6px 22px color-mix(in srgb, var(--c) 25%, rgba(0,0,0,.3))}}
.card.pinned{{border-color:rgba(255,211,122,.5)}}
.card.pinned::after{{content:'📌';position:absolute;top:10px;right:10px;font-size:12px;opacity:.85}}
.card.stale{{opacity:.55}}
.card.stale:hover{{opacity:1}}
.card.dragging{{opacity:.4;transform:scale(.96)}}
.card.merge-target{{border:2px dashed var(--c);background:color-mix(in srgb, var(--c) 22%, var(--surface));transform:scale(1.03)}}
.card-head{{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:8px}}
.card h3{{font-size:14.5px;font-weight:600;line-height:1.35;color:var(--text);word-break:break-word;padding-right:24px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;max-height:6em}}
.card .meta{{display:flex;gap:8px;align-items:center;font-size:11px;color:var(--text-m);margin-bottom:10px;letter-spacing:.3px;flex-wrap:wrap}}
.card .meta .sep{{opacity:.5}}
.card .ago{{color:var(--text-d);font-weight:500}}
.card .ago.fresh{{color:var(--ok)}}
.card .ask{{font-size:12.5px;line-height:1.55;color:var(--text-d);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;margin-bottom:12px}}
.card .ask:empty::before, .card .ask .empty{{content:'(无首问)';color:var(--text-m);font-style:italic}}
.card footer{{display:flex;gap:6px;align-items:center;flex-wrap:wrap}}

/* Group card */
.card.group{{background:linear-gradient(135deg, color-mix(in srgb, var(--c) 18%, var(--surface)), color-mix(in srgb, var(--c) 6%, var(--surface)));border:1.5px solid color-mix(in srgb, var(--c) 45%, var(--border))}}
.card.group::before{{width:6px}}
.group-badge{{display:inline-flex;align-items:center;gap:5px;background:color-mix(in srgb, var(--c) 35%, transparent);color:#fff;font-size:10.5px;font-weight:700;letter-spacing:.6px;padding:2px 9px;border-radius:100px;margin-bottom:6px;border:1px solid color-mix(in srgb, var(--c) 60%, transparent)}}
.group-members{{display:flex;flex-direction:column;gap:6px;margin:8px 0 10px;padding:8px;background:rgba(0,0,0,.18);border-radius:8px;border:1px solid var(--border)}}
.group-member{{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:5px 8px;border-radius:6px;font-size:11.5px;color:var(--text-d);transition:.15s;cursor:default}}
.group-member:hover{{background:rgba(255,255,255,.04)}}
.group-member .name{{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.group-member .pop{{opacity:0;transition:.15s;font-size:14px;line-height:1;color:var(--text-m);padding:2px 6px;border-radius:4px;cursor:pointer}}
.group-member:hover .pop{{opacity:1}}
.group-member .pop:hover{{background:rgba(232,122,106,.15);color:var(--danger)}}

.btn{{padding:6px 10px;border-radius:8px;font-size:11.5px;letter-spacing:.5px;color:var(--text-d);background:transparent;border:1px solid var(--border);transition:.15s;font-weight:500}}
.btn:hover{{background:var(--border);color:var(--text);border-color:var(--border-h)}}
.btn.primary{{color:var(--accent);border-color:rgba(232,164,120,.3)}}
.btn.primary:hover{{background:rgba(232,164,120,.15);border-color:var(--accent)}}
.btn.danger:hover{{background:rgba(232,122,106,.15);border-color:var(--danger);color:var(--danger)}}
.btn.icon{{padding:6px 8px;font-size:13px}}
.spacer{{flex:1}}

/* PRD Modal */
.backdrop{{position:fixed;inset:0;background:rgba(10,7,5,.78);backdrop-filter:blur(10px);z-index:90;display:none;align-items:flex-start;justify-content:center;padding:40px 20px;overflow-y:auto}}
.backdrop.show{{display:flex}}
.modal{{max-width:880px;width:100%;background:var(--bg2);border:1px solid var(--border-h);border-radius:20px;padding:0;box-shadow:0 20px 80px rgba(0,0,0,.6);overflow:hidden}}
.m-head{{padding:28px 32px 20px;border-bottom:1px solid var(--border);position:relative}}
.m-head::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--c)}}
.m-cat-row{{display:flex;align-items:center;gap:10px;margin-bottom:10px}}
.m-cat{{font-size:11px;letter-spacing:2px;color:var(--c);font-weight:600;text-transform:uppercase}}
.m-status{{font-size:10px;letter-spacing:1px;padding:2px 8px;border-radius:100px;background:rgba(158,208,184,.15);color:var(--ok);border:1px solid rgba(158,208,184,.3)}}
.m-status.interrupted{{background:rgba(232,164,120,.15);color:var(--accent);border-color:rgba(232,164,120,.3)}}
.m-status.empty{{background:rgba(255,255,255,.05);color:var(--text-m);border-color:var(--border)}}
.m-head h2{{font-size:24px;font-weight:600;margin-bottom:8px;line-height:1.3;letter-spacing:-.3px}}
.m-meta{{font-size:12px;color:var(--text-m);letter-spacing:.3px;display:flex;gap:14px;flex-wrap:wrap}}
.m-meta b{{color:var(--text-d);font-weight:500}}
.m-themes{{margin-top:14px;display:flex;gap:6px;flex-wrap:wrap}}
.m-themes .theme{{font-size:11px;padding:3px 10px;border-radius:100px;background:rgba(232,164,120,.1);color:var(--accent);border:1px solid rgba(232,164,120,.25)}}
.m-body{{padding:24px 32px}}
.m-section{{margin-bottom:24px}}
.m-section h3{{font-size:11px;letter-spacing:2.5px;color:var(--text-m);text-transform:uppercase;font-weight:600;margin-bottom:10px;display:flex;align-items:center;gap:8px}}
.m-section h3::before{{content:'';width:3px;height:11px;background:var(--c);border-radius:2px}}
.m-purpose{{font-size:14px;line-height:1.7;color:var(--text);background:var(--surface);border-left:3px solid var(--c);padding:14px 16px;border-radius:8px;white-space:pre-wrap;word-break:break-word}}

.m-chain{{display:flex;flex-direction:column;gap:8px}}
.m-step{{display:grid;grid-template-columns:32px 1fr;gap:12px;align-items:flex-start;padding:10px 12px;border-radius:10px;background:var(--surface);border:1px solid var(--border);transition:.2s;cursor:default}}
.m-step:hover{{border-color:var(--border-h)}}
.m-step .num{{font-size:11px;color:var(--text-m);font-family:'SF Mono',Consolas,monospace;background:rgba(255,255,255,.04);padding:4px 0;text-align:center;border-radius:6px;letter-spacing:.5px}}
.m-step .what{{font-size:13px;line-height:1.5;color:var(--text-d);min-width:0;word-break:break-word}}
.m-step .what b{{color:var(--text);font-weight:500;display:block;margin-bottom:3px;font-size:13.5px}}
.m-step .what .reply{{font-size:11.5px;color:var(--text-m);margin-top:4px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-style:italic}}
.m-step.no-reply{{opacity:.55}}
.m-step.no-reply .num{{color:var(--danger)}}

.m-arts{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px}}
.m-art{{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:10px;background:var(--surface);border:1px solid var(--border);font-size:12px;color:var(--text-d);transition:.15s}}
.m-art:hover{{border-color:var(--border-h);background:rgba(255,255,255,.03)}}
.m-art .icon{{font-size:18px;flex-shrink:0}}
.m-art .info{{min-width:0;flex:1}}
.m-art .name{{color:var(--text);font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12.5px}}
.m-art .sub{{font-size:10.5px;color:var(--text-m);margin-top:2px}}
.m-art.plan{{border-color:rgba(232,164,120,.3);background:rgba(232,164,120,.06)}}
.m-art.plan .name{{color:var(--accent)}}

.m-plan-preview{{font-size:12px;line-height:1.7;color:var(--text-d);background:#1a120e;border:1px solid var(--border);border-radius:10px;padding:14px 16px;font-family:-apple-system,'PingFang SC',sans-serif;max-height:320px;overflow-y:auto;white-space:pre-wrap;word-break:break-word}}
.m-plan-preview::-webkit-scrollbar{{width:6px}}
.m-plan-preview::-webkit-scrollbar-thumb{{background:var(--border-h);border-radius:3px}}

.m-foot{{padding:18px 32px;border-top:1px solid var(--border);display:flex;gap:10px;background:rgba(0,0,0,.15);flex-wrap:wrap}}
.m-empty{{font-size:12px;color:var(--text-m);font-style:italic;padding:6px 0}}

/* Toast */
.toast{{position:fixed;bottom:24px;left:50%;transform:translateX(-50%) translateY(30px);background:var(--bg2);border:1px solid var(--border-h);color:var(--text);padding:12px 22px;border-radius:100px;font-size:13px;opacity:0;transition:.3s;z-index:999;box-shadow:var(--shadow);letter-spacing:.3px}}
.toast.show{{opacity:1;transform:translateX(-50%) translateY(0)}}
.toast.err{{border-color:var(--danger);color:var(--danger)}}
.toast.ok{{border-color:var(--ok)}}

.empty-state{{text-align:center;padding:60px 20px;color:var(--text-m)}}
.empty-state .big{{font-size:40px;margin-bottom:10px;opacity:.5}}

/* Category picker dropdown */
.cat-picker{{background:var(--bg2);border:1px solid var(--border-h);border-radius:12px;padding:6px;box-shadow:0 12px 40px rgba(0,0,0,.5);min-width:200px;animation:cp-in .15s ease-out}}
@keyframes cp-in{{from{{opacity:0;transform:translateY(-4px)}}to{{opacity:1;transform:translateY(0)}}}}
.cat-picker .cp-title{{font-size:10px;letter-spacing:1.5px;color:var(--text-m);text-transform:uppercase;padding:6px 10px 8px}}
.cat-picker .cp-item{{display:flex;align-items:center;gap:9px;width:100%;padding:8px 10px;border-radius:8px;font-size:12.5px;color:var(--text-d);background:transparent;border:none;text-align:left;transition:.12s;cursor:pointer}}
.cat-picker .cp-item:hover{{background:color-mix(in srgb, var(--c) 18%, transparent);color:var(--text)}}
.cat-picker .cp-item.cur{{color:var(--text);background:rgba(255,255,255,.04)}}
.cat-picker .cp-item .dot{{width:8px;height:8px;border-radius:50%;background:var(--c);flex-shrink:0}}
.cat-picker .cp-item .tag{{font-size:9px;color:var(--text-m);margin-left:auto;letter-spacing:1px;text-transform:uppercase}}
</style></head>
<body><div class=app>
<div class=topbar>
  <h1>🗂️ Memory</h1>
  <span class=meta id=countMeta>{total} 段对话</span>
  <div style="flex:1"></div>
  <a href="/space" style="padding:7px 14px;border-radius:100px;background:linear-gradient(135deg,rgba(232,164,120,.2),rgba(247,146,178,.15));border:1px solid rgba(232,164,120,.4);color:var(--accent);font-size:12px;letter-spacing:1px;text-decoration:none;text-transform:uppercase;transition:.2s" onmouseover="this.style.background='linear-gradient(135deg,rgba(232,164,120,.35),rgba(247,146,178,.25))'" onmouseout="this.style.background='linear-gradient(135deg,rgba(232,164,120,.2),rgba(247,146,178,.15))'">✨ 作战空间</a>
</div>
<div class=hint>按 <kbd>/</kbd> 搜索 · 拖卡片到<b style="color:var(--accent)">另一卡片</b>=合并 · 拖到<b style="color:var(--ok)">列空白处</b>=改分类 · <kbd>📌</kbd> 固定 · <kbd>Esc</kbd> 关闭</div>

<div class=controls>
  <div class=search-row>
    <div class=search>
      <svg width=16 height=16 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2><circle cx=11 cy=11 r=7/><path d="m21 21-4.3-4.3"/></svg>
      <input id=q placeholder="搜索（支持中英双语，如「英语」能命中 English）" autocomplete=off>
      <span class=kbd>/</span>
    </div>
    <div class=sort>
      <button data-sort=recent class=active>最近</button>
      <button data-sort=oldest>最早</button>
      <button data-sort=active>最频繁</button>
    </div>
  </div>
  <div class=chips>
    <button class="chip all active" data-cat=all><span class=dot></span>全部</button>
    <button class="chip pinned" data-cat=pinned><span class=dot></span>📌 已固定</button>
    {chip_html}
  </div>
</div>

<div class=stats id=stats></div>
<div class=kanban id=kanban></div>
<div class=empty-state id=emptyState style="display:none"><div class=big>🔍</div><div>没有匹配的记忆。试试别的关键词。</div></div>

</div>

<div class=backdrop id=modal><div class=modal id=modalInner></div></div>
<div id=toast class=toast></div>

<script>
const DATA = {data_json};
const PINS = new Set(JSON.parse(localStorage.getItem('pins')||'[]'));
const state = {{q:'', cat:'all', sort:'recent'}};

// Bilingual synonym map (expand to cover your vocabulary freely)
const ALIASES = {{
  '英语':['english','英文'], 'english':['英语','英文'], '英文':['english','英语'],
  '学习':['learn','learning','study','成长'], 'learn':['学习'], 'learning':['学习','study'], 'study':['学习','learning'],
  '成长':['growth','growing','learning','学习'], 'growth':['成长'],
  '计划':['plan','planning'], 'plan':['计划','planning'], 'planning':['计划','plan'],
  '客户':['customer','client'], 'customer':['客户'], 'client':['客户'],
  '商务':['business'], 'business':['商务'],
  '技能':['skill','skills'], 'skill':['技能'], 'skills':['技能'],
  '数字分身':['digital clone','avatar','twin','clone'], '分身':['clone','avatar','twin'],
  '对话':['conversation','chat','dialog','dialogue'], 'chat':['对话'], 'conversation':['对话'], 'dialog':['对话'],
  '历史':['history','past'], 'history':['历史'], 'past':['历史'],
  '看板':['dashboard','kanban','board'], 'dashboard':['看板'], 'kanban':['看板'], 'board':['看板'],
  '工具':['tool','tools','utility'], 'tool':['工具'], 'tools':['工具'],
  '邮箱':['email','mail','mailbox'], 'email':['邮箱'], 'mail':['邮箱'],
  '窗口':['window'], 'window':['窗口'],
  '记忆':['memory','memories'], 'memory':['记忆'],
  '汇报':['summary','report','briefing','briefs'], 'summary':['汇报'], 'report':['汇报'], 'briefing':['汇报'],
  '老板':['boss','manager','leader','executive'], 'boss':['老板'], 'manager':['老板'],
  '模型':['model','models'], 'model':['模型'],
  '对比':['compare','comparison','vs','versus'], 'compare':['对比'], 'comparison':['对比'],
  '渠道':['channel','channels'], 'channel':['渠道'],
  '申请':['apply','application','request','justification'],
  '时延':['latency','delay'], 'latency':['时延'],
  '报价':['quote','pricing','quotation'], 'quote':['报价'], 'pricing':['报价'],
  '英语能力':['english','english skill'], '口语':['speaking','oral','conversation'],
  '演讲':['speech','presentation','speaking','public speaking'], 'speech':['演讲'],
  '谈判':['negotiation','negotiate'], 'negotiation':['谈判'],
  '配额':['quota','quotas'], 'quota':['配额'],
  '部署':['deploy','deployment','setup'], 'deploy':['部署'],
  '微信':['wechat','weixin'], 'wechat':['微信'],
  '清理':['clean','cleanup','tidy','organize'], 'cleanup':['清理'],
  '可视化':['visualize','visualization','visual'], 'visualize':['可视化'],
}};

function expandTokens(q){{
  const tokens = q.toLowerCase().trim().split(/\\s+/).filter(Boolean);
  return tokens.map(tok => {{
    const variants = new Set([tok]);
    (ALIASES[tok] || []).forEach(a => variants.add(a.toLowerCase()));
    // Reverse lookup: if tok is value of some key, add that key too
    for (const [k, vs] of Object.entries(ALIASES)) {{
      if (vs.map(v => v.toLowerCase()).includes(tok)) variants.add(k.toLowerCase());
    }}
    return [...variants];
  }});
}}
function matchesQuery(haystack, tokenGroups){{
  const h = haystack.toLowerCase();
  return tokenGroups.every(variants => variants.some(v => h.includes(v)));
}}

function daysAgo(iso){{
  const d=(Date.now()-new Date(iso).getTime())/86400000;
  if(d<1) return '今天';
  if(d<2) return '昨天';
  if(d<7) return Math.floor(d)+' 天前';
  if(d<30) return Math.floor(d/7)+' 周前';
  if(d<365) return Math.floor(d/30)+' 月前';
  return Math.floor(d/365)+' 年前';
}}
function isFresh(iso){{return (Date.now()-new Date(iso).getTime())/86400000 < 7}}
function isStale(iso){{return (Date.now()-new Date(iso).getTime())/86400000 > 60}}
function esc(s){{return (s||'').replace(/[&<>"']/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[m]))}}

function highlight(text, q){{
  if(!q) return esc(text);
  const groups = expandTokens(q);
  const all = [...new Set(groups.flat())].filter(t => t.length > 0)
    .sort((a,b) => b.length - a.length);  // longer first to avoid partial overlap
  if(!all.length) return esc(text);
  const re = new RegExp('(' + all.map(t => t.replace(/[.*+?^${{}}()|[\\]\\\\]/g,'\\\\$&')).join('|') + ')', 'ig');
  return esc(text).replace(re,'<mark style="background:rgba(232,164,120,.38);color:var(--text);border-radius:3px;padding:0 3px;font-weight:600">$1</mark>');
}}

function filtered(){{
  let arr = DATA.slice();
  if(state.cat==='pinned') arr = arr.filter(s=>PINS.has(s.id));
  else if(state.cat!=='all') arr = arr.filter(s=>s.cat===state.cat);
  if(state.q){{
    const groups = expandTokens(state.q);
    arr = arr.filter(s => matchesQuery(s.summary + ' ' + s.ask + ' ' + s.cat + ' ' + (s.body||''), groups));
  }}
  arr.sort((a,b)=>{{
    const pa=PINS.has(a.id), pb=PINS.has(b.id);
    if(pa!==pb) return pb-pa;
    if(state.sort==='oldest') return new Date(a.updated_iso)-new Date(b.updated_iso);
    if(state.sort==='active') return b.turns-a.turns;
    return new Date(b.updated_iso)-new Date(a.updated_iso);
  }});
  return arr;
}}

function renderStats(){{
  const arr = filtered();
  const fresh = arr.filter(s=>isFresh(s.updated_iso)).length;
  const pinned = arr.filter(s=>PINS.has(s.id)).length;
  const totalTurns = arr.reduce((a,s)=>a+s.turns,0);
  document.getElementById('stats').innerHTML = `
    <div class=stat><div class=n>${{arr.length}}</div><div class=l>显示中</div></div>
    <div class=stat><div class=n>${{fresh}}</div><div class=l>本周活跃</div></div>
    <div class=stat><div class=n>${{pinned}}</div><div class=l>已固定</div></div>
    <div class=stat><div class=n>${{totalTurns}}</div><div class=l>总交互</div></div>`;
}}

// Build category color lookup from server-side
const CAT_COLOR = {cat_color_json};
const CAT_ORDER = {cat_order_json};
const CAT_ICON = {cat_icon_json};

function bodySnippet(s, q){{
  if(!q || !s.body) return '';
  const groupsT = expandTokens(q);
  const head = (s.summary + ' ' + s.ask).toLowerCase();
  if(groupsT.every(vs => vs.some(v => head.includes(v)))) return '';
  if(!matchesQuery(s.body, groupsT)) return '';
  const all = [...new Set(groupsT.flat())].sort((a,b)=>b.length-a.length);
  const body = s.body;
  const lower = body.toLowerCase();
  let pos = -1;
  for(const t of all){{ pos = lower.indexOf(t); if(pos>=0) break; }}
  if(pos < 0) return '';
  const start = Math.max(0, pos-30), end = Math.min(body.length, pos+90);
  const slice = (start>0?'…':'') + body.slice(start, end) + (end<body.length?'…':'');
  return `<div style="font-size:11px;color:var(--text-m);background:rgba(232,164,120,.08);border-left:2px solid var(--accent);padding:6px 8px;border-radius:0 6px 6px 0;margin-bottom:8px">💬 ${{highlight(slice, q)}}</div>`;
}}

function cardHTML(s, q){{
  const snippet = bodySnippet(s, q);
  const pinned = PINS.has(s.id);
  const stale = isStale(s.updated_iso) && !pinned;
  const fresh = isFresh(s.updated_iso);
  const isGroup = s.is_primary && s.group_size > 1;
  const groupTitle = isGroup ? (s.group_name || s.summary) : s.summary;
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
  return `<article class="card ${{isGroup?'group':''}} ${{pinned?'pinned':''}} ${{stale?'stale':''}}" 
    style="--c:${{s.color}}" data-id="${{s.id}}" draggable="true"
    ondragstart="onDragStart(event,'${{s.id}}')" ondragend="onDragEnd(event)"
    ondragover="onDragOver(event,'${{s.id}}')" ondragleave="onDragLeave(event)" ondrop="onDrop(event,'${{s.id}}')"
    onclick="openModal('${{s.id}}')">
    ${{isGroup?`<div class=group-badge>🧩 合并任务 · ${{s.group_size}} 个会话</div>`:''}}
    <div class=card-head><h3>${{highlight(groupTitle, q)}}</h3></div>
    <div class=meta>
      <span class="ago ${{fresh?'fresh':''}}">${{daysAgo(s.updated_iso)}}</span>
      <span class=sep>·</span>
      <span>🔁 ${{s.turns}} 轮</span>
      <span class=sep>·</span>
      <span>${{s.date}}</span>
    </div>
    ${{membersHTML}}
    ${{snippet}}
    <div class=ask>${{s.ask?highlight(s.ask,q):'<span class=empty></span>'}}</div>
    <footer onclick="event.stopPropagation()">
      <button class="btn primary" onclick="resume('${{s.id}}')">▶ 继续</button>
      <button class="btn icon" onclick="togglePin('${{s.id}}')" title="固定">${{pinned?'📍':'📌'}}</button>
      <button class="btn icon" onclick="renameIt('${{s.id}}')" title="重命名">✎</button>
      <button class="btn icon" onclick="showCatPicker(event,'${{s.id}}')" title="移到分类">📁</button>
      <div class=spacer></div>
      <button class="btn icon danger" onclick="del_('${{s.id}}')" title="删除">🗑</button>
    </footer>
  </article>`;
}}

function renderGrid(){{
  const arr = filtered();
  // Hide non-primary group members from top level
  const visible = arr.filter(s => !s.group_id || s.is_primary);
  document.getElementById('countMeta').textContent = `${{visible.length}} / {total} 段对话`;
  document.getElementById('emptyState').style.display = visible.length?'none':'block';

  // Group by cat in CAT_ORDER
  const byCat = {{}};
  CAT_ORDER.forEach(c => byCat[c] = []);
  visible.forEach(s => {{ if(!byCat[s.cat]) byCat[s.cat]=[]; byCat[s.cat].push(s); }});

  const showCats = (state.cat==='all' || state.cat==='pinned') ? CAT_ORDER : [state.cat];
  const k = document.getElementById('kanban');
  k.innerHTML = showCats.map(c => {{
    const items = byCat[c] || [];
    if(state.q && items.length === 0) return '';  // hide empty cols when searching
    const color = CAT_COLOR[c] || '#a0aec0';
    const icon = (CAT_ICON[c] || c).split(' ')[0];
    const title = c.replace(/^[^\\s]+\\s*/, '');
    return `<div class=col style="--c:${{color}}" data-cat="${{esc(c)}}"
      ondragover="onColDragOver(event)" ondragleave="onColDragLeave(event)" ondrop="onColDrop(event)">
      <div class=col-head>
        <span class=ic>${{icon}}</span>
        <span class=title>${{esc(title)}}</span>
        <span class=count>${{items.length}}</span>
      </div>
      ${{items.length ? items.map(s=>cardHTML(s, state.q)).join('') : '<div class=col-empty>(空)</div>'}}
    </div>`;
  }}).join('');
}}

// ── Drag & drop merge ───────────────────────────────────────────
let DRAG_SID = null;
function onDragStart(e, sid){{
  DRAG_SID = sid;
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('text/plain', sid);
  e.currentTarget.classList.add('dragging');
}}
function onDragEnd(e){{
  document.querySelectorAll('.dragging').forEach(x=>x.classList.remove('dragging'));
  document.querySelectorAll('.merge-target').forEach(x=>x.classList.remove('merge-target'));
  document.querySelectorAll('.col.drop-here').forEach(x=>x.classList.remove('drop-here'));
  DRAG_SID = null;
}}
function onDragOver(e, sid){{
  if(!DRAG_SID || DRAG_SID === sid) return;
  e.preventDefault(); e.stopPropagation();
  e.dataTransfer.dropEffect = 'move';
  e.currentTarget.classList.add('merge-target');
}}
function onDragLeave(e){{ e.currentTarget.classList.remove('merge-target'); }}
async function onDrop(e, targetSid){{
  e.preventDefault(); e.stopPropagation();
  e.currentTarget.classList.remove('merge-target');
  if(!DRAG_SID || DRAG_SID === targetSid) return;
  const src = DATA.find(x=>x.id===DRAG_SID);
  const tgt = DATA.find(x=>x.id===targetSid);
  if(!src || !tgt) return;
  if(!confirm(`将「${{src.summary}}」合并到「${{tgt.summary}}」？\\n（可随时点 ✕ 拆分）`)) return;
  const r = await fetch('/groups/merge', {{method:'POST',
    headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{primary: targetSid, secondary: DRAG_SID}})}});
  if(r.ok){{ toast('已合并 ✓','ok'); setTimeout(()=>location.reload(), 400); }}
  else toast('合并失败','err');
}}
// Column-level drop = re-categorize (drag card onto blank column area)
function onColDragOver(e){{
  if(!DRAG_SID) return;
  e.preventDefault();
  e.currentTarget.classList.add('drop-here');
}}
function onColDragLeave(e){{
  // only clear when truly leaving the column
  if(e.currentTarget.contains(e.relatedTarget)) return;
  e.currentTarget.classList.remove('drop-here');
}}
async function onColDrop(e){{
  e.preventDefault();
  const col = e.currentTarget;
  col.classList.remove('drop-here');
  const newCat = col.dataset.cat;
  const sid = DRAG_SID;
  if(!sid || !newCat) return;
  const src = DATA.find(x=>x.id===sid);
  if(!src || src.cat === newCat) return;
  const r = await fetch('/sessions/recat', {{method:'POST',
    headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{id: sid, cat: newCat}})}});
  if(r.ok){{ toast(`已移到「${{newCat}}」 ✓`,'ok'); setTimeout(()=>location.reload(), 400); }}
  else toast('移动失败','err');
}}

async function unmerge(sid){{
  if(!confirm('从合并中移出？')) return;
  const r = await fetch('/groups/unmerge', {{method:'POST',
    headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{id: sid}})}});
  if(r.ok){{ toast('已拆分 ✓','ok'); setTimeout(()=>location.reload(), 400); }}
  else toast('拆分失败','err');
}}

// Quick category picker (no drag needed) — for offscreen columns
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
  // Reposition if overflow bottom
  const mr = menu.getBoundingClientRect();
  if(mr.bottom > window.innerHeight - 8){{
    menu.style.top = Math.max(8, rect.top - mr.height - 6) + 'px';
  }}
  if(mr.right > window.innerWidth - 8){{
    menu.style.left = (window.innerWidth - mr.width - 12) + 'px';
  }}
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

// Auto-scroll while dragging — so offscreen columns become reachable
let _scrollRAF = null, _scrollVy = 0;
function _scrollTick(){{
  if(_scrollVy !== 0){{
    window.scrollBy(0, _scrollVy);
    _scrollRAF = requestAnimationFrame(_scrollTick);
  }} else {{
    _scrollRAF = null;
  }}
}}
document.addEventListener('dragover', e => {{
  if(!DRAG_SID) return;
  const y = e.clientY, h = window.innerHeight;
  const edge = 90;
  if(y < edge) _scrollVy = -Math.ceil((edge - y) / 4);
  else if(y > h - edge) _scrollVy = Math.ceil((y - (h - edge)) / 4);
  else _scrollVy = 0;
  if(_scrollVy !== 0 && _scrollRAF == null) _scrollRAF = requestAnimationFrame(_scrollTick);
}});
document.addEventListener('dragend', () => {{ _scrollVy = 0; }});
document.addEventListener('drop', () => {{ _scrollVy = 0; }});

function rerender(){{renderStats();renderGrid()}}

// Controls
document.getElementById('q').addEventListener('input',e=>{{state.q=e.target.value;rerender()}});
document.querySelectorAll('.chip').forEach(c=>c.addEventListener('click',()=>{{
  document.querySelectorAll('.chip').forEach(x=>x.classList.remove('active'));
  c.classList.add('active'); state.cat=c.dataset.cat; rerender();
}}));
document.querySelectorAll('.sort button').forEach(b=>b.addEventListener('click',()=>{{
  document.querySelectorAll('.sort button').forEach(x=>x.classList.remove('active'));
  b.classList.add('active'); state.sort=b.dataset.sort; rerender();
}}));
document.addEventListener('keydown',e=>{{
  if(e.key==='/' && e.target.tagName!=='INPUT'){{e.preventDefault();document.getElementById('q').focus()}}
  if(e.key==='Escape'){{closeModal();document.getElementById('q').blur()}}
}});

// Modal — rich PRD view fetched from /session
async function openModal(id){{
  const modal = document.getElementById('modal');
  const inner = document.getElementById('modalInner');
  inner.innerHTML = '<div style="padding:60px;text-align:center;color:var(--text-m)">⏳ 加载中…</div>';
  modal.classList.add('show');
  let d;
  try{{
    const r = await fetch('/session?id='+id);
    if(!r.ok) throw new Error('http '+r.status);
    d = await r.json();
  }} catch(e){{
    inner.innerHTML = `<div style="padding:40px;color:var(--danger)">加载失败：${{e.message}}</div>`; return;
  }}

  const fmtBytes = b => b<1024 ? b+' B' : b<1048576 ? (b/1024).toFixed(1)+' KB' : (b/1048576).toFixed(1)+' MB';
  const iconFor = a => a.kind==='plan'?'📋':a.kind==='doc'?'📄':a.kind==='data'?'🗂️':'📎';

  const chainHtml = d.chain.length ? d.chain.map(c => `
    <div class="m-step ${{c.has_reply?'':'no-reply'}}">
      <div class=num>#${{c.i}}</div>
      <div class=what>
        <b>${{esc(c.user) || '<i style="opacity:.5">(无内容)</i>'}}</b>
        ${{c.has_reply ? `<div class=reply>↪ ${{esc(c.reply_preview)}}</div>` : '<div class=reply style="color:var(--danger)">↪ (无回复)</div>'}}
      </div>
    </div>`).join('') : '<div class=m-empty>(暂无对话轮次)</div>';

  const artsHtml = d.artifacts.length ? `<div class=m-arts>${{d.artifacts.map(a => `
    <div class="m-art ${{a.kind==='plan'?'plan':''}}" title="${{esc(a.abs)}}">
      <div class=icon>${{iconFor(a)}}</div>
      <div class=info>
        <div class=name>${{esc(a.path)}}</div>
        <div class=sub>${{fmtBytes(a.size)}} · ${{a.mtime}}</div>
      </div>
    </div>`).join('')}}</div>` : '<div class=m-empty>(无文件产出)</div>';

  const themesHtml = d.themes.length ? `<div class=m-themes>${{d.themes.map(t => `<span class=theme>${{esc(t)}}</span>`).join('')}}</div>` : '';

  const planHtml = d.plan_preview ? `
    <div class=m-section>
      <h3>📋 计划文档预览（plan.md）</h3>
      <div class=m-plan-preview>${{esc(d.plan_preview)}}${{d.plan_preview.length>=1500?'\\n\\n[已截断，完整内容见 plan.md]':''}}</div>
    </div>` : '';

  inner.innerHTML = `
    <div class=m-head style="--c:${{d.cat_color}}">
      <div class=m-cat-row>
        <span class=m-cat style="color:${{d.cat_color}}">${{esc(d.cat)}}</span>
        <span class="m-status ${{d.status}}">${{esc(d.status_label)}}</span>
      </div>
      <h2>${{esc(d.summary)}}</h2>
      <div class=m-meta>
        <span><b>${{d.turns}}</b> 轮交互</span>
        <span>📅 始于 ${{d.created_at.slice(0,10)}}</span>
        <span>🕰️ 活跃于 ${{d.updated_at.slice(0,10)}}</span>
        ${{d.artifacts.length?`<span>📎 <b>${{d.artifacts.length}}</b> 个产出物</span>`:''}}
      </div>
      ${{themesHtml}}
    </div>
    <div class=m-body style="--c:${{d.cat_color}}">
      <div class=m-section>
        <h3>🎯 目的（首问）</h3>
        <div class=m-purpose>${{esc(d.first_ask) || '(无首问)'}}</div>
      </div>
      ${{planHtml}}
      <div class=m-section>
        <h3>🔗 链路（${{d.chain.length}} 轮对话）</h3>
        <div class=m-chain>${{chainHtml}}</div>
      </div>
      <div class=m-section>
        <h3>📦 产出物</h3>
        ${{artsHtml}}
      </div>
    </div>
    <div class=m-foot>
      <button class="btn primary" onclick="resume('${{d.id}}')">▶ 继续对话</button>
      <button class="btn" onclick="togglePin('${{d.id}}')">${{PINS.has(d.id)?'📍 取消固定':'📌 固定'}}</button>
      <button class="btn" onclick="renameIt('${{d.id}}')">✎ 重命名</button>
      ${{d.artifacts.length?`<button class="btn" onclick="openFolder('${{d.id}}')">📂 打开文件夹</button>`:''}}
      <div class=spacer></div>
      <button class="btn danger" onclick="del_('${{d.id}}')">🗑 删除</button>
    </div>`;
}}
async function openFolder(id){{
  await fetch('/openfolder?id='+id, {{method:'POST'}});
  toast('已尝试打开文件夹');
}}
function closeModal(){{document.getElementById('modal').classList.remove('show')}}
document.getElementById('modal').addEventListener('click',e=>{{if(e.target.id==='modal')closeModal()}});

// Actions
function toast(msg, kind){{
  const t=document.getElementById('toast');
  t.textContent=msg; t.className='toast show '+(kind||'ok');
  setTimeout(()=>t.className='toast '+(kind||''),2400);
}}
async function resume(id){{
  const r=await fetch('/resume?id='+id,{{method:'POST'}});
  toast(r.ok?'✓ 已在新终端打开':'✗ 启动失败', r.ok?'ok':'err');
}}
function togglePin(id){{
  if(PINS.has(id)){{PINS.delete(id);toast('已取消固定')}}
  else{{PINS.add(id);toast('已固定到顶部')}}
  localStorage.setItem('pins', JSON.stringify([...PINS]));
  rerender();
}}
async function renameIt(id){{
  const s = DATA.find(x=>x.id===id); if(!s) return;
  const name = prompt('重命名会话：', s.summary);
  if(!name || name===s.summary) return;
  const r = await fetch('/rename?id='+id,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{name}})}});
  if(r.ok){{ s.summary=name; toast('已重命名'); rerender(); closeModal(); }}
  else toast('重命名失败','err');
}}
async function del_(id){{
  const s = DATA.find(x=>x.id===id); if(!s) return;
  if(!confirm(`删除「${{s.summary}}」？\\n该会话全部历史将被清除，不可恢复。`)) return;
  const r=await fetch('/delete?id='+id,{{method:'POST'}});
  if(r.ok){{
    const i=DATA.findIndex(x=>x.id===id); if(i>-1) DATA.splice(i,1);
    PINS.delete(id); localStorage.setItem('pins', JSON.stringify([...PINS]));
    closeModal(); rerender(); toast('已删除');
  }} else toast('删除失败','err');
}}

rerender();
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def address_string(self): return self.client_address[0]  # skip reverse DNS
    def _send(self, code, body, ctype='text/html; charset=utf-8'):
        b = body.encode('utf-8') if isinstance(body, str) else body
        self.send_response(code); self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(b))); self.end_headers()
        self.wfile.write(b)
    def do_GET(self):
        p = urlparse(self.path)
        if p.path in ('/', '/index.html'):
            self._send(200, render())
        elif p.path == '/space':
            from space_view import render_space
            self._send(200, render_space(fetch_sessions, CAT_COLORS))
        elif p.path == '/session':
            q = parse_qs(p.query); sid = (q.get('id') or [''])[0]
            if not re.fullmatch(r'[0-9a-f-]{36}', sid):
                self._send(400, '{"error":"bad id"}', 'application/json'); return
            d = session_detail(sid)
            if not d:
                self._send(404, '{"error":"not found"}', 'application/json'); return
            self._send(200, json.dumps(d, ensure_ascii=False), 'application/json; charset=utf-8')
        else:
            self._send(404, 'not found', 'text/plain')
    def do_POST(self):
        p = urlparse(self.path); q = parse_qs(p.query); sid = (q.get('id') or [''])[0]
        try:
            length = int(self.headers.get('Content-Length', 0) or 0)
            body = self.rfile.read(length) if length else b''
            payload = {}
            if body:
                try: payload = json.loads(body.decode('utf-8'))
                except Exception: payload = {}

            if p.path == '/sessions/recat':
                t = payload.get('id',''); cat = (payload.get('cat') or '').strip()
                if not re.fullmatch(r'[0-9a-f-]{36}', t):
                    self._send(400, 'bad id', 'text/plain'); return
                if cat and cat not in CAT_COLORS:
                    self._send(400, 'bad cat', 'text/plain'); return
                set_session_cat(t, cat); self._send(200, 'ok', 'text/plain'); return
            if p.path == '/groups/merge':
                primary = payload.get('primary',''); secondary = payload.get('secondary','')
                if not (re.fullmatch(r'[0-9a-f-]{36}', primary) and re.fullmatch(r'[0-9a-f-]{36}', secondary)):
                    self._send(400, 'bad ids', 'text/plain'); return
                merge_sessions(primary, secondary); self._send(200, 'ok', 'text/plain'); return
            if p.path == '/groups/unmerge':
                t = payload.get('id','')
                if not re.fullmatch(r'[0-9a-f-]{36}', t):
                    self._send(400, 'bad id', 'text/plain'); return
                unmerge_session(t); self._send(200, 'ok', 'text/plain'); return
            if p.path == '/groups/rename':
                gid = payload.get('group_id',''); name = (payload.get('name') or '').strip()
                if not re.fullmatch(r'[0-9a-f-]{36}', gid) or not name:
                    self._send(400, 'bad', 'text/plain'); return
                rename_group(gid, name); self._send(200, 'ok', 'text/plain'); return

            if not re.fullmatch(r'[0-9a-f-]{36}', sid):
                self._send(400, 'bad id', 'text/plain'); return
            if p.path == '/resume':
                resume_session(sid); self._send(200, 'ok', 'text/plain')
            elif p.path == '/delete':
                delete_session(sid); self._send(200, 'ok', 'text/plain')
            elif p.path == '/rename':
                name = (payload.get('name') or '').strip()
                if not name:
                    self._send(400, 'empty', 'text/plain'); return
                rename_session(sid, name); self._send(200, 'ok', 'text/plain')
            elif p.path == '/openfolder':
                folder = STATE_DIR / sid
                if folder.exists():
                    subprocess.Popen(['explorer.exe', str(folder)], shell=False)
                self._send(200, 'ok', 'text/plain')
            else:
                self._send(404, 'nope', 'text/plain')
        except Exception as e:
            self._send(500, f'err: {e}', 'text/plain')

if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    url = f'http://localhost:{PORT}/'
    print(f'🚀 Copilot 看板已启动: {url}')
    print('   Ctrl+C 停止服务')
    try: 
        if '--no-browser' not in sys.argv: webbrowser.open(url)
    except: pass
    try: HTTPServer(('127.0.0.1', PORT), H).serve_forever()
    except KeyboardInterrupt: print('\n已停止')
