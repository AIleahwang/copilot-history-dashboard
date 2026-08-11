"""Copilot 对话看板 · 本地服务
运行: python server.py  → 浏览器访问 http://localhost:8765
"""
import sqlite3, os, re, html, json, shutil, subprocess, webbrowser, sys, uuid, threading, time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone

HOME = Path(os.environ['USERPROFILE'])
DB = HOME / '.copilot' / 'session-store.db'
STATE_DIR = HOME / '.copilot' / 'session-state'
PORT = 8765
PROJECT_LABEL = 'General / Personal'
EXCLUDED_CWD_MARKERS = ('clawpilot',)
SCOUT_CWD_MARKER = 'scout'
GITHUB_DESKTOP_HOST_TYPE = 'github'
AUTO_CLEAN_EMPTY_SESSIONS = os.environ.get(
    'COPILOT_DASHBOARD_KEEP_EMPTY', ''
).strip().lower() not in ('1', 'true', 'yes')
EMPTY_SESSION_GRACE_SECONDS = 180
EMPTY_CLEANUP_INTERVAL_SECONDS = 30
_EMPTY_CLEANUP_LOCK = threading.Lock()

def session_scope_sql(alias='s'):
    cwd = f"LOWER(COALESCE({alias}.cwd,''))"
    return ' AND '.join(f"{cwd} NOT LIKE '%{marker}%'" for marker in EXCLUDED_CWD_MARKERS)

def is_scout_cwd(cwd):
    return SCOUT_CWD_MARKER in (cwd or '').lower()

def is_github_desktop_session(host_type):
    return (host_type or '').lower() == GITHUB_DESKTOP_HOST_TYPE

def scoped_existing_ids(ids):
    valid = sorted({sid for sid in ids if re.fullmatch(r'[0-9a-f-]{36}', sid or '')})
    if not valid:
        return set()
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    try:
        qs = ','.join('?' for _ in valid)
        rows = con.execute(
            f"SELECT s.id FROM sessions s WHERE s.id IN ({qs}) AND {session_scope_sql('s')}",
            valid
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        con.close()

def session_in_scope(sid):
    return sid in scoped_existing_ids([sid])

def require_session_in_scope(sid):
    if not session_in_scope(sid):
        raise PermissionError(f'session is outside {PROJECT_LABEL} dashboard scope')

CATS = [
    ('🐙 GitHub Desktop', []),
    ('🛰️ Scout', ['scout']),
    ('🧠 技能 / 数字分身', ['skill', 'openclaw', '分身', 'wechat']),
    ('💼 客户 & 商务', ['ptu', 'datazone', 'claude', 'gpt', 'justification', 'tpm', 'bedrock']),
    ('📊 汇报 & 沟通', ['老板', '汇报', 'summary', 'business']),
    ('📚 学习 & 成长', ['english', '英语', '学习', 'learning', 'plan', '成长']),
    ('🛠️ 工具 & 自助', ['email', '窗口', 'visualize', 'history', 'coding', 'dashboard', '看板']),
]

def categorize(summary, ask, cwd='', host_type=''):
    if is_github_desktop_session(host_type):
        return '🐙 GitHub Desktop'
    if is_scout_cwd(cwd):
        return '🛰️ Scout'
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
    s = _SCOUT_CONTEXT_RE.sub('', unwrap_conversation_prompt(raw or '')).strip()
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

_SKILL_CONTEXT_RE = re.compile(r'<skill-context.*?</skill-context>', re.S)
_SYSTEM_REMINDER_RE = re.compile(r'<system_reminder>.*?</system_reminder>', re.S)
_CURRENT_DATETIME_RE = re.compile(r'<current_datetime>.*?</current_datetime>\s*', re.S)
_SCOUT_CONTEXT_RE = re.compile(r'\[[^\]]*Scout context:.*?\]\s*', re.S)
_CLI_PROMPT_RE = re.compile(r'^\s*[❯>]+\s*', re.M)
_ATTACHMENT_MARKER_RE = re.compile(r'\[(?:📷|🖼️|📎|📄)?\s*copilot-[^\]]+\]', re.I)
_NOISY_REPLY_MARKERS = (
    'response was interrupted due to a server error',
    'failed to get response from the ai model',
    'attached image or document is too large',
    'try a smaller attachment or fewer attachments',
)

class UnsafeResumeError(RuntimeError):
    pass

def unwrap_conversation_prompt(text):
    s = text or ''
    low = s.lower()
    if ('here is the conversation' in low or low.startswith('user:')) and 'user:' in low and 'assistant:' in low:
        m = re.search(r'user:\s*(.*?)(?:\s+assistant:|$)', s, flags=re.I | re.S)
        if m:
            return m.group(1).strip()
    return s

def clean_turn_user(raw):
    s = raw or ''
    s = _SKILL_CONTEXT_RE.sub('', s)
    s = _SYSTEM_REMINDER_RE.sub('', s)
    s = _CURRENT_DATETIME_RE.sub('', s)
    s = _SCOUT_CONTEXT_RE.sub('', s)
    s = _CLI_PROMPT_RE.sub('', s)
    s = unwrap_conversation_prompt(s)
    return re.sub(r'\s+', ' ', s).strip()

def is_noisy_reply(raw):
    s = re.sub(r'\s+', ' ', (raw or '').lower()).strip()
    return bool(s) and any(m in s for m in _NOISY_REPLY_MARKERS)

def canonical_turn_user(text):
    s = _ATTACHMENT_MARKER_RE.sub('[attachment]', (text or '').lower())
    return re.sub(r'\s+', ' ', s).strip()

def is_duplicate_prompt(a, b):
    if not a or not b:
        return False
    if a == b:
        return True
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 40 and long.startswith(short)

def build_clean_chain(turns):
    chain = []
    skipped = 0
    for t in turns:
        raw_user = t['user_message'] or ''
        reply = (t['assistant_response'] or '').strip()
        user = clean_turn_user(raw_user)
        has_reply = bool(reply) and not is_noisy_reply(reply)

        if not user and has_reply:
            if chain and not chain[-1]['has_reply']:
                chain[-1]['has_reply'] = True
                chain[-1]['reply_preview'] = reply[:240]
                chain[-1]['reply_len'] = len(reply)
            else:
                skipped += 1
            continue
        if not user and not has_reply:
            skipped += 1
            continue

        item = {
            'i': t['turn_index'],
            'time': t['timestamp'],
            'user': user[:300],
            'user_full_len': len(raw_user),
            'has_reply': has_reply,
            'reply_preview': reply[:240] if has_reply else '',
            'reply_len': len(reply) if has_reply else 0,
            'repeat_count': 1,
            '_canon': canonical_turn_user(user),
            '_has_attachment': bool(_ATTACHMENT_MARKER_RE.search(raw_user)),
        }

        if chain and not item['has_reply'] and not chain[-1]['has_reply'] and is_duplicate_prompt(chain[-1].get('_canon'), item['_canon']):
            chain[-1]['repeat_count'] = chain[-1].get('repeat_count', 1) + 1
            chain[-1]['time'] = item['time']
            chain[-1]['_has_attachment'] = chain[-1].get('_has_attachment') or item['_has_attachment']
            skipped += 1
            continue
        chain.append(item)

    for item in chain:
        item.pop('_canon', None)
    return chain, skipped

def _parse_db_timestamp(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

def _session_is_recent(row, grace_seconds):
    if grace_seconds <= 0:
        return False
    touched = _parse_db_timestamp(row['updated_at'] or row['created_at'])
    if touched is None:
        return True
    return (datetime.now(timezone.utc) - touched).total_seconds() < grace_seconds

def _session_has_active_marker(sid):
    folder = STATE_DIR / sid
    if not folder.exists():
        return False
    for marker in folder.glob('inuse.*'):
        match = re.fullmatch(r'inuse\.(\d+)(?:\.lock)?', marker.name)
        if not match:
            return True
        try:
            os.kill(int(match.group(1)), 0)
            return True
        except OSError:
            try:
                marker.unlink()
            except OSError:
                pass
    return False

def _session_is_truly_empty(summary, turns):
    """Only remove shell sessions that contain neither a title nor a real turn."""
    chain, _ = build_clean_chain(turns)
    return not chain and not (summary or '').strip()

def _session_related_tables(con):
    related = []
    rows = con.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
    """).fetchall()
    for row in rows:
        name = row[0]
        if name == 'sessions':
            continue
        quoted = name.replace('"', '""')
        columns = {col[1] for col in con.execute(f'PRAGMA table_info("{quoted}")')}
        if 'session_id' in columns:
            related.append(name)
    return related

def _delete_session_rows(con, sid):
    for table in _session_related_tables(con):
        quoted = table.replace('"', '""')
        try:
            con.execute(f'DELETE FROM "{quoted}" WHERE session_id=?', (sid,))
        except sqlite3.OperationalError:
            if table != 'search_index':
                raise
    con.execute("DELETE FROM sessions WHERE id=?", (sid,))

def cleanup_empty_sessions(grace_seconds=EMPTY_SESSION_GRACE_SECONDS):
    """Delete inactive sessions with no meaningful user or assistant content."""
    if not AUTO_CLEAN_EMPTY_SESSIONS or not DB.exists():
        return []
    if not _EMPTY_CLEANUP_LOCK.acquire(blocking=False):
        return []
    deleted = []
    try:
        ro = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
        ro.row_factory = sqlite3.Row
        try:
            session_rows = ro.execute(f"""
                SELECT s.id, s.summary, s.created_at, s.updated_at
                FROM sessions s
                WHERE {session_scope_sql('s')}
            """).fetchall()
            turn_rows = ro.execute(f"""
                SELECT t.session_id, t.turn_index, t.user_message,
                       t.assistant_response, t.timestamp
                FROM turns t
                JOIN sessions s ON s.id=t.session_id
                WHERE {session_scope_sql('s')}
                ORDER BY t.session_id, t.turn_index
            """).fetchall()
        finally:
            ro.close()

        turns_by_sid = {}
        for turn in turn_rows:
            turns_by_sid.setdefault(turn['session_id'], []).append(turn)
        candidates = [
            row for row in session_rows
            if _session_is_truly_empty(
                row['summary'], turns_by_sid.get(row['id'], []))
            and not _session_is_recent(row, grace_seconds)
            and not _session_has_active_marker(row['id'])
        ]
        if not candidates:
            return []

        con = sqlite3.connect(DB, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            con.execute('BEGIN IMMEDIATE')
            for candidate in candidates:
                sid = candidate['id']
                current = con.execute(f"""
                    SELECT s.id, s.summary, s.created_at, s.updated_at
                    FROM sessions s
                    WHERE s.id=? AND {session_scope_sql('s')}
                """, (sid,)).fetchone()
                if not current or _session_is_recent(current, grace_seconds) or _session_has_active_marker(sid):
                    continue
                current_turns = con.execute("""
                    SELECT turn_index, user_message, assistant_response, timestamp
                    FROM turns WHERE session_id=? ORDER BY turn_index
                """, (sid,)).fetchall()
                if not _session_is_truly_empty(current['summary'], current_turns):
                    continue
                _delete_session_rows(con, sid)
                deleted.append(sid)
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

        for sid in deleted:
            folder = STATE_DIR / sid
            if folder.exists():
                shutil.rmtree(folder)
        return deleted
    finally:
        _EMPTY_CLEANUP_LOCK.release()

def start_empty_cleanup_worker():
    if not AUTO_CLEAN_EMPTY_SESSIONS:
        return

    def worker():
        while True:
            time.sleep(EMPTY_CLEANUP_INTERVAL_SECONDS)
            try:
                removed = cleanup_empty_sessions()
                if removed:
                    print(f'🧹 自动清理 {len(removed)} 个空白会话')
            except (sqlite3.Error, OSError) as error:
                print(f'⚠ 空白会话自动清理失败: {error}', file=sys.stderr)

    threading.Thread(
        target=worker,
        name='copilot-empty-session-cleaner',
        daemon=True,
    ).start()

def resume_block_reason_from_chain(chain):
    if not chain:
        return ''
    last = chain[-1]
    if not last.get('has_reply') and last.get('_has_attachment'):
        return '最后一轮包含图片附件且没有成功回复，直接继续会重复触发 5MB 限制；请压缩图片或减少附件后新开对话。'
    if not last.get('has_reply') and last.get('repeat_count', 1) > 1:
        return '最后一轮是连续重复的未完成请求，直接继续可能再次重试失败；建议新开对话重新发送精简后的请求。'
    return ''

def session_resume_block_reason(sid):
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    try:
        turns = con.execute("""SELECT turn_index, user_message, assistant_response, timestamp
                               FROM turns WHERE session_id=? ORDER BY turn_index""", (sid,)).fetchall()
    finally:
        con.close()
    chain, _ = build_clean_chain(turns)
    return resume_block_reason_from_chain(chain)

def fetch_sessions():
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(f"""
      SELECT s.id, s.summary, s.created_at, s.updated_at, s.cwd,
        s.host_type, s.repository,
        (SELECT COUNT(*) FROM turns WHERE session_id=s.id) turns,
        (SELECT user_message FROM turns WHERE session_id=s.id AND user_message IS NOT NULL ORDER BY turn_index LIMIT 1) ask
      FROM sessions s
      WHERE {session_scope_sql('s')}
      ORDER BY COALESCE(s.updated_at, s.created_at) DESC
    """).fetchall()
    turn_rows = con.execute(f"""
      SELECT t.session_id, t.turn_index, t.user_message, t.assistant_response, t.timestamp
      FROM turns t
      JOIN sessions s ON s.id=t.session_id
      WHERE {session_scope_sql('s')}
      ORDER BY t.session_id, t.turn_index
    """).fetchall()
    turns_by_sid = {}
    for tr in turn_rows:
        turns_by_sid.setdefault(tr['session_id'], []).append(tr)
    clean_meta = {}
    bodies = {}
    for session_id, tlist in turns_by_sid.items():
        chain, skipped = build_clean_chain(tlist)
        clean_meta[session_id] = {
            'turns': len(chain),
            'skipped_turns': skipped,
            'resume_block_reason': resume_block_reason_from_chain(chain),
        }
        bodies[session_id] = ' '.join(c['user'] for c in chain)
    con.close()
    groups = load_groups()
    overrides = load_overrides()
    sid_to_group = {}
    for gid, info in groups.items():
        for m in info.get('members', []):
            sid_to_group[m] = (gid, info)
    out = []
    for r in rows:
        ask = clean_turn_user(r['ask'])
        meta = clean_meta.get(r['id'], {'turns': r['turns'], 'skipped_turns': 0, 'resume_block_reason': ''})
        if AUTO_CLEAN_EMPTY_SESSIONS and _session_is_truly_empty(
                r['summary'], turns_by_sid.get(r['id'], [])):
            continue
        gid_info = sid_to_group.get(r['id'])
        gid = gid_info[0] if gid_info else None
        ginfo = gid_info[1] if gid_info else None
        is_primary = bool(ginfo and ginfo.get('primary') == r['id'])
        # Strip skill-context blocks + collapse whitespace, cap to 4000 chars
        body = re.sub(r'<skill-context.*?</skill-context>', '', bodies.get(r['id'], ''), flags=re.S)
        body = re.sub(r'\s+', ' ', body).strip()[:8000]
        if is_github_desktop_session(r['host_type']):
            cat = '🐙 GitHub Desktop'
        elif is_scout_cwd(r['cwd']):
            cat = '🛰️ Scout'
        else:
            cat = overrides.get(r['id']) or categorize(r['summary'], r['ask'], r['cwd'], r['host_type'])
        out.append(dict(id=r['id'], summary=clean_summary(r['summary'], ask),
                        raw_summary=r['summary'] or '',
                        date=r['created_at'][:10],
                        updated=(r['updated_at'] or r['created_at'])[:10],
                        updated_iso=(r['updated_at'] or r['created_at']),
                        turns=meta['turns'],
                        raw_turns=r['turns'],
                        skipped_turns=meta['skipped_turns'],
                        resume_block_reason=meta['resume_block_reason'],
                        ask=ask[:240],
                        body=body,
                        cat=cat,
                        source='github-desktop' if is_github_desktop_session(r['host_type']) else 'cli',
                        repository=r['repository'] or '',
                        group_id=gid,
                        is_primary=is_primary,
                        group_name=(ginfo or {}).get('name', '') if ginfo else '',
                        group_size=len(ginfo['members']) if ginfo else 0))
    return out

def delete_session(sid):
    """从 DB 和 session-state 文件夹彻底删除"""
    require_session_in_scope(sid)
    con = sqlite3.connect(DB, timeout=10)
    try:
        _delete_session_rows(con, sid)
        con.commit()
    finally:
        con.close()
    folder = STATE_DIR / sid
    if folder.exists():
        shutil.rmtree(folder)

def rename_session(sid, new_name):
    require_session_in_scope(sid)
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
        try:
            raw = json.loads(GROUPS_FILE.read_text(encoding='utf-8'))
            ids = []
            for gid, info in raw.items():
                ids.append(gid)
                ids.extend(info.get('members', []))
                if info.get('primary'):
                    ids.append(info['primary'])
            allowed = scoped_existing_ids(ids)
            filtered = {}
            for gid, info in raw.items():
                members = [m for m in info.get('members', []) if m in allowed]
                primary = info.get('primary') if info.get('primary') in allowed else (members[0] if members else None)
                if primary and primary not in members:
                    members.insert(0, primary)
                if len(members) > 1 and (gid in allowed or primary):
                    filtered[primary or gid] = {'name': info.get('name', ''), 'primary': primary, 'members': members}
            return filtered
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
    require_session_in_scope(primary)
    require_session_in_scope(secondary)
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
    require_session_in_scope(sid)
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
        try:
            raw = json.loads(OVERRIDES_FILE.read_text(encoding='utf-8'))
            allowed = scoped_existing_ids(raw.keys())
            return {sid: cat for sid, cat in raw.items() if sid in allowed}
        except Exception: return {}
    return {}

def save_overrides(d):
    OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
    OVERRIDES_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')

def set_session_cat(sid, cat):
    require_session_in_scope(sid)
    d = load_overrides()
    if cat:
        d[sid] = cat
    else:
        d.pop(sid, None)
    save_overrides(d)

# ─── Mission Queue (floating task radar for /space) ─────────────────────────
MISSION_FILE = HOME / '.copilot' / 'mission-queue.json'
MISSION_LANES = ('NOW', 'NEXT', 'LOOP', 'PARKED')
MISSION_PRIORITIES = ('P0', 'P1', 'P2')
DEFAULT_MISSIONS = [
    {
        'id': 'ai-digital-twin',
        'title': 'AI 数字分身计划',
        'lane': 'NOW',
        'priority': 'P0',
        'type': 'project',
        'cadence': '本周',
        'next': '梳理 v1 功能边界、人格设定、数据源与验证链路',
        'query': '数字分身 personal ai agent openclaw wechat',
    },
    {
        'id': 'bd-leads',
        'title': 'BD Leads',
        'lane': 'NOW',
        'priority': 'P0',
        'type': 'loop',
        'cadence': '每周一 / 三 / 五',
        'next': '更新 10-20 个潜在客户，标注下一步触达动作',
        'query': 'BD leads startup outreach pipeline',
    },
    {
        'id': 'aesthetic-biweekly',
        'title': '审美双周报',
        'lane': 'LOOP',
        'priority': 'P1',
        'type': 'loop',
        'cadence': '每两周',
        'next': '收集 5 个视觉案例，输出可复用的审美 pattern',
        'query': '审美 aesthetic visual design summary',
    },
    {
        'id': 'copilot-history-dashboard',
        'title': 'Copilot History Dashboard',
        'lane': 'NEXT',
        'priority': 'P1',
        'type': 'project',
        'cadence': '本周',
        'next': '打磨 Mission Queue，完成 v2 README / GitHub 更新',
        'query': 'copilot history dashboard 看板 mission queue',
    },
    {
        'id': 'follow-builders',
        'title': 'Follow Builders Skill',
        'lane': 'LOOP',
        'priority': 'P1',
        'type': 'loop',
        'cadence': '每周',
        'next': '新增 / 复盘 3 个 AI builder，提炼输入到输出的启发',
        'query': 'follow builders skill ai builder digest',
    },
    {
        'id': 'english-writing',
        'title': '英语表达 / 商务写作',
        'lane': 'PARKED',
        'priority': 'P2',
        'type': 'loop',
        'cadence': '每周',
        'next': '复盘 3 条高频表达，沉淀到可复用话术库',
        'query': 'english 商务写作 expression learning',
    },
]

def _mission_now():
    return datetime.now().isoformat(timespec='seconds')

def _normalize_mission(m, index=0):
    title = str(m.get('title') or '').strip()[:80]
    if not title:
        title = 'Untitled Mission'
    lane = str(m.get('lane') or 'NEXT').strip().upper()
    if lane not in MISSION_LANES:
        lane = 'NEXT'
    priority = str(m.get('priority') or 'P2').strip().upper()
    if priority not in MISSION_PRIORITIES:
        priority = 'P2'
    typ = str(m.get('type') or 'project').strip().lower()
    if typ not in ('project', 'loop'):
        typ = 'project'
    status = str(m.get('status') or 'open').strip().lower()
    if status not in ('open', 'completed'):
        status = 'open'
    sid = str(m.get('session_id') or '').strip()
    if sid and (not re.fullmatch(r'[0-9a-f-]{36}', sid) or not session_in_scope(sid)):
        sid = ''
    raw_done = m.get('done_session_ids') or []
    if not isinstance(raw_done, list):
        raw_done = []
    done_ids = [str(x).strip() for x in raw_done if re.fullmatch(r'[0-9a-f-]{36}', str(x).strip())]
    allowed_done = scoped_existing_ids(done_ids) if done_ids else set()
    mid = str(m.get('id') or '').strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{3,64}', mid):
        mid = 'm-' + uuid.uuid4().hex[:10]
    now = _mission_now()
    return {
        'id': mid,
        'title': title,
        'lane': lane,
        'priority': priority,
        'type': typ,
        'cadence': str(m.get('cadence') or '').strip()[:60],
        'next': str(m.get('next') or '').strip()[:180],
        'query': str(m.get('query') or title).strip()[:160],
        'session_id': sid,
        'done_session_ids': [x for x in done_ids if x in allowed_done],
        'status': status,
        'created_at': str(m.get('created_at') or now),
        'updated_at': str(m.get('updated_at') or now),
        'completed_at': str(m.get('completed_at') or '') if status == 'completed' else '',
        'sort_order': int(m.get('sort_order') or index),
    }

def load_missions():
    if not MISSION_FILE.exists():
        missions = [_normalize_mission(m, i) for i, m in enumerate(DEFAULT_MISSIONS)]
        save_missions(missions)
        return missions
    try:
        raw = json.loads(MISSION_FILE.read_text(encoding='utf-8'))
        items = raw.get('missions', raw) if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            return []
        return [_normalize_mission(m, i) for i, m in enumerate(items) if isinstance(m, dict)]
    except Exception:
        return []

def save_missions(missions):
    MISSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    MISSION_FILE.write_text(json.dumps({'missions': missions}, ensure_ascii=False, indent=2), encoding='utf-8')

def upsert_mission(payload):
    missions = load_missions()
    mid = str(payload.get('id') or '').strip()
    now = _mission_now()
    found = False
    for i, m in enumerate(missions):
        if mid and m['id'] == mid:
            merged = {**m, **payload, 'id': m['id'], 'updated_at': now}
            missions[i] = _normalize_mission(merged, i)
            found = True
            break
    if not found:
        item = dict(payload)
        item.setdefault('id', 'm-' + uuid.uuid4().hex[:10])
        item.setdefault('created_at', now)
        item['updated_at'] = now
        item.setdefault('sort_order', len(missions))
        missions.append(_normalize_mission(item, len(missions)))
    save_missions(missions)
    return missions

def complete_mission(mid):
    missions = load_missions()
    now = _mission_now()
    changed = False
    for m in missions:
        if m['id'] == mid:
            m['status'] = 'completed'
            m['completed_at'] = now
            m['updated_at'] = now
            changed = True
            break
    if changed:
        save_missions(missions)
    return changed

def delete_mission(mid):
    missions = load_missions()
    kept = [m for m in missions if m['id'] != mid]
    if len(kept) == len(missions):
        return False
    save_missions(kept)
    return True

def complete_mission_session(mid, sid):
    require_session_in_scope(sid)
    missions = load_missions()
    now = _mission_now()
    changed = False
    for m in missions:
        if m['id'] == mid:
            done = set(m.get('done_session_ids') or [])
            done.add(sid)
            m['done_session_ids'] = sorted(done)
            m['updated_at'] = now
            changed = True
            break
    if changed:
        save_missions(missions)
    return changed

def session_detail(sid):
    """Return structured PRD-like summary of one session."""
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    s = con.execute(f"SELECT * FROM sessions s WHERE s.id=? AND {session_scope_sql('s')}", (sid,)).fetchone()
    if not s:
        con.close(); return None
    turns = con.execute("""SELECT turn_index, user_message, assistant_response, timestamp
                           FROM turns WHERE session_id=? ORDER BY turn_index""", (sid,)).fetchall()
    con.close()

    chain, skipped_turns = build_clean_chain(turns)

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
    resume_block_reason = resume_block_reason_from_chain(chain)
    if resume_block_reason:
        status = ('interrupted', '含未完成附件请求')
    elif not chain:
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
        'raw_turns': len(turns),
        'skipped_turns': skipped_turns,
        'first_ask': chain[0]['user'] if chain else '',
        'last_ask': chain[-1]['user'] if chain else '',
        'cat': categorize(s['summary'], chain[0]['user'] if chain else '', s['cwd'], s['host_type']),
        'cat_color': CAT_COLORS.get(categorize(s['summary'], chain[0]['user'] if chain else '', s['cwd'], s['host_type']), '#a0aec0'),
        'chain': chain,
        'artifacts': artifacts,
        'plan_preview': plan_preview,
        'status': status[0],
        'status_label': status[1],
        'resume_block_reason': resume_block_reason,
        'themes': themes,
        'duration_days': max(1, (datetime.fromisoformat(s['created_at'].replace('Z','+00:00')).date()
                                 .toordinal() - datetime.fromisoformat((s['updated_at'] or s['created_at']).replace('Z','+00:00')).date().toordinal()) * -1) if s['updated_at'] else 0,
    }

def resume_session(sid):
    """新开一个 Windows Terminal/cmd 窗口运行 copilot --resume"""
    require_session_in_scope(sid)
    block_reason = session_resume_block_reason(sid)
    if block_reason:
        raise UnsafeResumeError(block_reason)
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
    '🐙 GitHub Desktop': '#f0f6fc',
    '🛰️ Scout': '#9FE870',
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
.clean-status{{display:inline-flex;align-items:center;gap:5px;color:var(--ok);font-size:11px;padding:3px 9px;border:1px solid rgba(158,208,184,.25);background:rgba(158,208,184,.08);border-radius:100px}}
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
  transition:border-color .2s, box-shadow .2s, opacity .2s, filter .2s;
}}
.col.drop-here{{border-color:var(--c);box-shadow:0 0 0 2px color-mix(in srgb, var(--c) 50%, transparent), 0 8px 30px rgba(0,0,0,.25)}}
.col-head{{display:flex;align-items:center;gap:10px;padding:6px 6px 12px;border-bottom:1px solid color-mix(in srgb, var(--c) 28%, transparent);margin-bottom:12px}}
.col[data-reorderable=true] .col-head{{cursor:grab;user-select:none;-webkit-user-select:none;touch-action:none}}
.module-grip{{color:color-mix(in srgb,var(--c) 52%,var(--text-m));font-size:17px;line-height:1;letter-spacing:-4px;padding-right:4px;opacity:.55;transition:opacity .15s,color .15s}}
.col[data-reorderable=true] .col-head:hover .module-grip{{opacity:1;color:var(--c)}}
.kanban.module-editing .col:not(.module-placeholder){{animation:moduleWiggle .16s ease-in-out infinite alternate;transform-origin:50% 10%}}
.kanban.module-editing .col:nth-child(even):not(.module-placeholder){{animation-direction:alternate-reverse}}
@keyframes moduleWiggle{{from{{transform:rotate(-.28deg)}}to{{transform:rotate(.28deg)}}}}
.col.module-placeholder{{opacity:.24;filter:saturate(.35);border-style:dashed;pointer-events:none}}
.module-drag-ghost{{position:fixed!important;z-index:1000!important;margin:0!important;pointer-events:none!important;overflow:hidden!important;opacity:.94;cursor:grabbing;transform:rotate(1.2deg) scale(1.025);box-shadow:0 28px 70px rgba(0,0,0,.55),0 0 0 2px color-mix(in srgb,var(--c) 65%,transparent)!important;transition:none!important}}
.col-head .ic{{font-size:18px}}
.col-head .title{{flex:1;color:#fff;font-weight:600;letter-spacing:.2px;text-shadow:0 1px 0 rgba(0,0,0,.25);font-size:14px}}
.col-head .count{{background:color-mix(in srgb, var(--c) 28%, transparent);color:#fff;padding:2px 10px;border-radius:100px;font-size:11px;font-weight:700;letter-spacing:.5px;border:1px solid color-mix(in srgb, var(--c) 50%, transparent)}}
.col-body{{overflow:visible;position:relative}}
.col-body.expanded{{max-height:min(720px, calc(100vh - 220px));overflow-y:auto;overscroll-behavior:contain;padding-right:3px;scrollbar-width:thin;scrollbar-color:var(--c) transparent}}
.col-body.expanded::-webkit-scrollbar{{width:6px}}
.col-body.expanded::-webkit-scrollbar-thumb{{background:color-mix(in srgb,var(--c) 42%,transparent);border-radius:3px}}
.col-more{{width:100%;margin:4px 0 2px;padding:9px 10px;border-radius:11px;border:1px dashed color-mix(in srgb,var(--c) 45%,transparent);background:color-mix(in srgb,var(--c) 10%,rgba(0,0,0,.16));color:color-mix(in srgb,var(--c) 35%,#fff);font-size:11.5px;letter-spacing:.8px}}
.col-more:hover{{border-style:solid;background:color-mix(in srgb,var(--c) 17%,rgba(0,0,0,.22));color:#fff}}
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
/* ── Celebration animations (delete poof + merge halo) ──────────── */
.card.poof{{animation:poof .55s cubic-bezier(.4,.0,.2,1) forwards;pointer-events:none}}
@keyframes poof{{
  0%{{transform:scale(1);opacity:1;filter:blur(0)}}
  40%{{transform:scale(1.08) rotate(-2deg);opacity:.95;filter:blur(0)}}
  100%{{transform:scale(.2) rotate(8deg);opacity:0;filter:blur(8px)}}
}}
.card.merge-glow{{animation:mergeGlow .9s cubic-bezier(.2,.8,.2,1)}}
@keyframes mergeGlow{{
  0%{{box-shadow:0 0 0 0 color-mix(in srgb, var(--c) 60%, transparent)}}
  50%{{box-shadow:0 0 0 18px color-mix(in srgb, var(--c) 0%, transparent), 0 0 38px color-mix(in srgb, var(--c) 70%, transparent);transform:scale(1.04)}}
  100%{{box-shadow:0 0 0 0 transparent}}
}}
#fx-canvas{{position:fixed;inset:0;pointer-events:none;z-index:9999}}
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
.group-members{{display:flex;flex-direction:column;gap:6px;margin:8px 0 10px;padding:8px;background:rgba(0,0,0,.18);border-radius:8px;border:1px solid var(--border);max-height:180px;overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin;scrollbar-color:var(--c) transparent}}
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
  {'<span class=clean-status title="空白会话会在安全缓冲期后从数据库和本地状态目录中彻底删除">🧹 空白自动清理</span>' if AUTO_CLEAN_EMPTY_SESSIONS else ''}
  <div style="flex:1"></div>
  <a href="/space" style="padding:7px 14px;border-radius:100px;background:linear-gradient(135deg,rgba(232,164,120,.2),rgba(247,146,178,.15));border:1px solid rgba(232,164,120,.4);color:var(--accent);font-size:12px;letter-spacing:1px;text-decoration:none;text-transform:uppercase;transition:.2s" onmouseover="this.style.background='linear-gradient(135deg,rgba(232,164,120,.35),rgba(247,146,178,.25))'" onmouseout="this.style.background='linear-gradient(135deg,rgba(232,164,120,.2),rgba(247,146,178,.15))'">✨ 作战空间</a>
</div>
<div class=hint>按 <kbd>/</kbd> 搜索 · <b style="color:var(--accent)">长按模块标题</b>拖动排序 · 拖卡片到<b style="color:var(--accent)">另一卡片</b>=合并 · 拖到<b style="color:var(--ok)">列空白处</b>=改分类 · <kbd>📌</kbd> 固定 · <kbd>Esc</kbd> 关闭</div>

<div class=controls>
  <div class=search-row>
    <div class=search>
      <svg width=16 height=16 viewBox="0 0 24 24" fill=none stroke=currentColor stroke-width=2><circle cx=11 cy=11 r="7"/><path d="m21 21-4.3-4.3"/></svg>
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
<canvas id=fx-canvas></canvas>

<script>
const DATA = {data_json};
const PINS = new Set(JSON.parse(localStorage.getItem('pins')||'[]'));
const COL_EXPANDED_KEY = 'classic_col_expanded_v1';
const COL_LIMIT = 4;
const COL_EXPANDED = new Set(JSON.parse(localStorage.getItem(COL_EXPANDED_KEY)||'[]'));
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
const DEFAULT_CAT_ORDER = {cat_order_json};
const CAT_ORDER_KEY = 'classic_category_order_v1';
const CAT_ICON = {cat_icon_json};
function normalizeCategoryOrder(value){{
  const requested = Array.isArray(value) ? value : [];
  const valid = requested.filter((cat, index) =>
    DEFAULT_CAT_ORDER.includes(cat) && requested.indexOf(cat) === index);
  DEFAULT_CAT_ORDER.forEach(cat => {{ if(!valid.includes(cat)) valid.push(cat); }});
  return valid;
}}
function loadCategoryOrder(){{
  try{{ return normalizeCategoryOrder(JSON.parse(localStorage.getItem(CAT_ORDER_KEY)||'[]')); }}
  catch(e){{ return DEFAULT_CAT_ORDER.slice(); }}
}}
let CAT_ORDER = loadCategoryOrder();
function saveCategoryOrder(){{
  localStorage.setItem(CAT_ORDER_KEY, JSON.stringify(CAT_ORDER));
}}

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
function toggleColItems(e, cat){{
  e.stopPropagation();
  if(COL_EXPANDED.has(cat)) COL_EXPANDED.delete(cat); else COL_EXPANDED.add(cat);
  localStorage.setItem(COL_EXPANDED_KEY, JSON.stringify([...COL_EXPANDED]));
  renderGrid();
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
  const canReorder = !state.q && showCats.length > 1 &&
    (state.cat === 'all' || state.cat === 'pinned');
  const k = document.getElementById('kanban');
  k.innerHTML = showCats.map(c => {{
    const items = byCat[c] || [];
    if(state.q && items.length === 0) return '';  // hide empty cols when searching
    const expanded = COL_EXPANDED.has(c) || !!state.q || state.cat !== 'all';
    const shown = expanded ? items : items.slice(0, COL_LIMIT);
    const hidden = Math.max(0, items.length - shown.length);
    const color = CAT_COLOR[c] || '#a0aec0';
    const icon = (CAT_ICON[c] || c).split(' ')[0];
    const title = c.replace(/^[^\\s]+\\s*/, '');
    return `<div class=col style="--c:${{color}}" data-cat="${{esc(c)}}" data-reorderable="${{canReorder}}"
      ondragover="onColDragOver(event)" ondragleave="onColDragLeave(event)" ondrop="onColDrop(event)">
      <div class=col-head ${{canReorder?'onpointerdown="modulePressStart(event)" oncontextmenu="event.preventDefault()"':''}}
        title="${{canReorder?'长按后拖动模块排序':''}}">
        <span class=ic>${{icon}}</span>
        <span class=title>${{esc(title)}}</span>
        <span class=count>${{items.length}}</span>
        ${{canReorder?'<span class=module-grip aria-hidden=true>⠿</span>':''}}
      </div>
      <div class="col-body ${{expanded?'expanded':''}}">
        ${{items.length ? shown.map(s=>cardHTML(s, state.q)).join('') : '<div class=col-empty>(空)</div>'}}
        ${{hidden?`<button class=col-more onclick="toggleColItems(event,'${{esc(c)}}')">展开剩余 ${{hidden}} 个</button>`:''}}
        ${{expanded && items.length>COL_LIMIT && state.cat==='all' && !state.q?`<button class=col-more onclick="toggleColItems(event,'${{esc(c)}}')">收起到 ${{COL_LIMIT}} 个</button>`:''}}
      </div>
    </div>`;
  }}).join('');
}}

// ── iOS-style long-press module reorder ─────────────────────────
const MODULE_HOLD_MS = 360;
let MODULE_PRESS = null;

function removeModulePointerListeners(){{
  document.removeEventListener('pointermove', modulePressMove);
  document.removeEventListener('pointerup', modulePressEnd);
  document.removeEventListener('pointercancel', modulePressCancel);
}}
function modulePressStart(e){{
  if(MODULE_PRESS || DRAG_SID || (e.pointerType === 'mouse' && e.button !== 0)) return;
  const col = e.currentTarget.closest('.col');
  if(!col || col.dataset.reorderable !== 'true') return;
  e.preventDefault();
  MODULE_PRESS = {{
    pointerId:e.pointerId, col,
    startX:e.clientX, startY:e.clientY, x:e.clientX, y:e.clientY,
    active:false, originalOrder:CAT_ORDER.slice(), timer:null, ghost:null,
  }};
  MODULE_PRESS.timer = setTimeout(activateModuleDrag, MODULE_HOLD_MS);
  document.addEventListener('pointermove', modulePressMove, {{passive:false}});
  document.addEventListener('pointerup', modulePressEnd);
  document.addEventListener('pointercancel', modulePressCancel);
}}
function activateModuleDrag(){{
  const press = MODULE_PRESS;
  if(!press || press.active || !press.col.isConnected) return;
  press.active = true;
  const rect = press.col.getBoundingClientRect();
  press.grabX = press.x - rect.left;
  press.grabY = press.y - rect.top;
  press.ghostWidth = rect.width;
  press.ghostHeight = Math.min(rect.height, window.innerHeight * .72);
  press.ghost = press.col.cloneNode(true);
  press.ghost.classList.add('module-drag-ghost');
  press.ghost.classList.remove('module-placeholder', 'drop-here');
  press.ghost.removeAttribute('data-reorderable');
  press.ghost.querySelectorAll('[data-id]').forEach(node => node.removeAttribute('data-id'));
  press.ghost.querySelectorAll('button').forEach(button => button.tabIndex = -1);
  Object.assign(press.ghost.style, {{
    width:press.ghostWidth+'px', height:press.ghostHeight+'px',
  }});
  document.body.appendChild(press.ghost);
  press.col.classList.add('module-placeholder');
  document.getElementById('kanban').classList.add('module-editing');
  document.body.style.userSelect = 'none';
  if(navigator.vibrate) navigator.vibrate(24);
  positionModuleGhost(press.x, press.y);
}}
function positionModuleGhost(x, y){{
  const press = MODULE_PRESS;
  if(!press || !press.ghost) return;
  const left = Math.max(8, Math.min(
    window.innerWidth - press.ghostWidth - 8, x - press.grabX));
  const top = Math.max(8, Math.min(
    window.innerHeight - press.ghostHeight - 8, y - press.grabY));
  press.ghost.style.left = left+'px';
  press.ghost.style.top = top+'px';
}}
function animateModuleShift(grid, mutate){{
  const columns = [...grid.children].filter(node => node.classList.contains('col'));
  const before = new Map(columns.map(node => [node, node.getBoundingClientRect()]));
  mutate();
  columns.forEach(node => {{
    const first = before.get(node), last = node.getBoundingClientRect();
    const dx = first.left - last.left, dy = first.top - last.top;
    if(Math.abs(dx) > 1 || Math.abs(dy) > 1){{
      node.animate([
        {{translate:`${{dx}}px ${{dy}}px`}},
        {{translate:'0 0'}},
      ], {{duration:230, easing:'cubic-bezier(.2,.8,.2,1)'}});
    }}
  }});
}}
function moveModulePlaceholder(x, y){{
  const press = MODULE_PRESS;
  if(!press || !press.active) return;
  const grid = document.getElementById('kanban');
  const source = press.col;
  const others = [...grid.children].filter(
    node => node.classList.contains('col') && node !== source);
  if(!others.length) return;
  const pointNode = document.elementFromPoint(x, y);
  let target = pointNode && pointNode.closest ? pointNode.closest('.col') : null;
  if(!target || target === source){{
    target = others.reduce((nearest, node) => {{
      const rect = node.getBoundingClientRect();
      const distance = Math.hypot(
        x - (rect.left + rect.width / 2),
        y - (rect.top + rect.height / 2));
      return !nearest || distance < nearest.distance ? {{node, distance}} : nearest;
    }}, null).node;
  }}
  const rect = target.getBoundingClientRect();
  const sameRow = y >= rect.top && y <= rect.bottom;
  const after = sameRow ? x > rect.left + rect.width / 2
                        : y > rect.top + rect.height / 2;
  if((!after && source.nextElementSibling === target) ||
     (after && target.nextElementSibling === source)) return;
  const anchor = after ? target.nextElementSibling : target;
  animateModuleShift(grid, () => grid.insertBefore(source, anchor));
}}
function modulePressMove(e){{
  const press = MODULE_PRESS;
  if(!press || e.pointerId !== press.pointerId) return;
  press.x = e.clientX; press.y = e.clientY;
  if(!press.active){{
    if(Math.hypot(e.clientX-press.startX, e.clientY-press.startY) > 9){{
      clearTimeout(press.timer);
      removeModulePointerListeners();
      MODULE_PRESS = null;
    }}
    return;
  }}
  e.preventDefault();
  positionModuleGhost(e.clientX, e.clientY);
  moveModulePlaceholder(e.clientX, e.clientY);
}}
function cleanupModuleDrag(){{
  const press = MODULE_PRESS;
  if(!press) return;
  clearTimeout(press.timer);
  removeModulePointerListeners();
  if(press.ghost) press.ghost.remove();
  press.col.classList.remove('module-placeholder');
  document.getElementById('kanban').classList.remove('module-editing');
  document.body.style.userSelect = '';
}}
function modulePressEnd(e){{
  const press = MODULE_PRESS;
  if(!press || e.pointerId !== press.pointerId) return;
  if(press.active){{
    const visibleOrder = [...document.getElementById('kanban').children]
      .filter(node => node.classList.contains('col'))
      .map(node => node.dataset.cat);
    const visible = new Set(visibleOrder);
    CAT_ORDER = normalizeCategoryOrder([
      ...visibleOrder, ...CAT_ORDER.filter(cat => !visible.has(cat)),
    ]);
    saveCategoryOrder();
    cleanupModuleDrag();
    MODULE_PRESS = null;
    toast('模块位置已保存 ✓','ok');
    return;
  }}
  cleanupModuleDrag();
  MODULE_PRESS = null;
}}
function modulePressCancel(){{
  cancelModuleDrag(true);
}}
function cancelModuleDrag(restore){{
  const press = MODULE_PRESS;
  if(!press) return;
  if(restore && press.active){{
    CAT_ORDER = press.originalOrder;
  }}
  cleanupModuleDrag();
  MODULE_PRESS = null;
  if(restore && press.active) renderGrid();
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
  if(r.ok){{
    const tgtEl = e.currentTarget;
    const rect = tgtEl.getBoundingClientRect();
    celebrateMerge(rect);
    tgtEl.classList.remove('merge-glow'); void tgtEl.offsetWidth; tgtEl.classList.add('merge-glow');
    toast('🧩 同类项已合并 · 思路汇流','ok');
    setTimeout(()=>location.reload(), 900);
  }}
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
  if(e.key==='Escape'){{cancelModuleDrag(true);closeModal();document.getElementById('q').blur()}}
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
        ${{c.repeat_count>1 ? `<div class=reply style="color:#fbbf24">已折叠 ${{c.repeat_count}} 次重复失败尝试</div>` : ''}}
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
        ${{d.skipped_turns?`<span>🧹 已隐藏 <b>${{d.skipped_turns}}</b> 条系统/重复噪音</span>`:''}}
        <span>📅 始于 ${{d.created_at.slice(0,10)}}</span>
        <span>🕰️ 活跃于 ${{d.updated_at.slice(0,10)}}</span>
        ${{d.artifacts.length?`<span>📎 <b>${{d.artifacts.length}}</b> 个产出物</span>`:''}}
      </div>
      ${{d.resume_block_reason?`<div style="margin-top:12px;padding:10px 12px;border:1px solid rgba(245,158,11,.45);background:rgba(245,158,11,.12);border-radius:14px;color:#fbbf24;font-size:12px;line-height:1.6">⚠ ${{esc(d.resume_block_reason)}}</div>`:''}}
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

// ── Celebration FX: WebAudio synth + canvas confetti ───────────
let _ac=null;
function _audio(){{ if(!_ac){{ try{{_ac=new (window.AudioContext||window.webkitAudioContext)()}}catch(e){{_ac=null}} }} return _ac; }}
function _tone(freq, dur, type, vol, when){{
  const ac=_audio(); if(!ac) return;
  const t0=ac.currentTime+(when||0);
  const o=ac.createOscillator(), g=ac.createGain();
  o.type=type||'sine'; o.frequency.value=freq;
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(vol||0.18, t0+0.015);
  g.gain.exponentialRampToValueAtTime(0.0001, t0+dur);
  o.connect(g); g.connect(ac.destination);
  o.start(t0); o.stop(t0+dur+0.02);
}}
function chimeDelete(){{
  // descending: closure, entropy release
  _tone(880,.18,'triangle',.18, 0);
  _tone(659,.22,'triangle',.16, .08);
  _tone(440,.32,'sine',    .14, .18);
}}
function chimeMerge(){{
  // ascending arpeggio: constructive
  _tone(523,.12,'triangle',.16, 0);
  _tone(659,.12,'triangle',.16, .07);
  _tone(784,.14,'triangle',.18, .14);
  _tone(1046,.22,'sine',   .14, .22);
}}

const _fx={{c:null,ctx:null,parts:[],raf:0}};
function _fxInit(){{
  if(_fx.c) return;
  _fx.c=document.getElementById('fx-canvas');
  _fx.ctx=_fx.c.getContext('2d');
  const resize=()=>{{const r=devicePixelRatio||1;_fx.c.width=innerWidth*r;_fx.c.height=innerHeight*r;_fx.c.style.width=innerWidth+'px';_fx.c.style.height=innerHeight+'px';_fx.ctx.setTransform(r,0,0,r,0,0)}};
  resize(); addEventListener('resize',resize);
}}
function _fxLoop(){{
  const ctx=_fx.ctx; ctx.clearRect(0,0,innerWidth,innerHeight);
  const alive=[];
  for(const p of _fx.parts){{
    p.vy+=p.g; p.x+=p.vx; p.y+=p.vy; p.vx*=0.99; p.rot+=p.vr; p.life-=1;
    if(p.life>0 && p.y<innerHeight+30){{
      const a=Math.min(1, p.life/30);
      ctx.save(); ctx.globalAlpha=a; ctx.translate(p.x,p.y); ctx.rotate(p.rot);
      ctx.fillStyle=p.color;
      if(p.shape==='rect'){{ ctx.fillRect(-p.s/2,-p.s/2,p.s,p.s*.4); }}
      else{{ ctx.beginPath(); ctx.arc(0,0,p.s/2,0,Math.PI*2); ctx.fill(); }}
      ctx.restore(); alive.push(p);
    }}
  }}
  _fx.parts=alive;
  if(alive.length) _fx.raf=requestAnimationFrame(_fxLoop);
  else{{ cancelAnimationFrame(_fx.raf); _fx.raf=0; ctx.clearRect(0,0,innerWidth,innerHeight); }}
}}
function confettiBurst(x, y, colors, count, spread){{
  _fxInit();
  count=count||80; spread=spread||Math.PI*1.4;
  const dir=-Math.PI/2; // upward
  for(let i=0;i<count;i++){{
    const a=dir + (Math.random()-.5)*spread;
    const v=4+Math.random()*7;
    _fx.parts.push({{
      x:x, y:y, vx:Math.cos(a)*v, vy:Math.sin(a)*v,
      g:0.18+Math.random()*.05, rot:Math.random()*Math.PI, vr:(Math.random()-.5)*.3,
      s:5+Math.random()*7, life:60+Math.random()*40,
      color: colors[(Math.random()*colors.length)|0],
      shape: Math.random()<.55?'rect':'circle',
    }});
  }}
  if(!_fx.raf) _fx.raf=requestAnimationFrame(_fxLoop);
}}
function celebrateDelete(rect){{
  chimeDelete();
  const cx=rect?rect.left+rect.width/2:innerWidth/2;
  const cy=rect?rect.top+rect.height/2:innerHeight/2;
  confettiBurst(cx, cy, ['#9FE870','#FFD17A','#ffffff','#7B7B7B','#a8d4b8'], 70, Math.PI*1.6);
}}
function celebrateMerge(rect){{
  chimeMerge();
  const cx=rect?rect.left+rect.width/2:innerWidth/2;
  const cy=rect?rect.top+rect.height/2:innerHeight/2;
  confettiBurst(cx, cy, ['#9FE870','#22d3a8','#f472b6','#a78bfa','#ffffff'], 55, Math.PI*1.2);
}}

// Actions
function toast(msg, kind){{
  const t=document.getElementById('toast');
  t.textContent=msg; t.className='toast show '+(kind||'ok');
  setTimeout(()=>t.className='toast '+(kind||''),2400);
}}
async function resume(id){{
  const r=await fetch('/resume?id='+id,{{method:'POST'}});
  const msg = r.ok ? '✓ 已在新终端打开' : (await r.text() || '✗ 启动失败');
  toast(msg, r.ok?'ok':'err');
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
  const cardEl = document.querySelector(`[data-id="${{id}}"]`);
  const rect = cardEl ? cardEl.getBoundingClientRect() : null;
  const r=await fetch('/delete?id='+id,{{method:'POST'}});
  if(r.ok){{
    celebrateDelete(rect);
    if(cardEl){{ cardEl.classList.add('poof'); }}
    setTimeout(()=>{{
      const i=DATA.findIndex(x=>x.id===id); if(i>-1) DATA.splice(i,1);
      PINS.delete(id); localStorage.setItem('pins', JSON.stringify([...PINS]));
      closeModal(); rerender(); toast('✨ 已清理 · 熵 -1','ok');
    }}, 480);
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
        elif p.path == '/missions':
            self._send(200, json.dumps({'missions': load_missions()}, ensure_ascii=False), 'application/json; charset=utf-8')
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
            if p.path == '/missions/upsert':
                self._send(200, json.dumps({'missions': upsert_mission(payload)}, ensure_ascii=False), 'application/json; charset=utf-8'); return
            if p.path == '/missions/complete':
                mid = str(payload.get('id') or '').strip()
                if not re.fullmatch(r'[A-Za-z0-9_-]{3,64}', mid):
                    self._send(400, 'bad id', 'text/plain'); return
                ok = complete_mission(mid)
                self._send(200 if ok else 404, 'ok' if ok else 'not found', 'text/plain'); return
            if p.path == '/missions/delete':
                mid = str(payload.get('id') or '').strip()
                if not re.fullmatch(r'[A-Za-z0-9_-]{3,64}', mid):
                    self._send(400, 'bad id', 'text/plain'); return
                ok = delete_mission(mid)
                self._send(200 if ok else 404, 'ok' if ok else 'not found', 'text/plain'); return
            if p.path == '/missions/session-done':
                mid = str(payload.get('id') or '').strip()
                t = str(payload.get('session_id') or '').strip()
                if not re.fullmatch(r'[A-Za-z0-9_-]{3,64}', mid) or not re.fullmatch(r'[0-9a-f-]{36}', t):
                    self._send(400, 'bad id', 'text/plain'); return
                ok = complete_mission_session(mid, t)
                self._send(200 if ok else 404, 'ok' if ok else 'not found', 'text/plain'); return

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
                require_session_in_scope(sid)
                folder = STATE_DIR / sid
                if folder.exists():
                    subprocess.Popen(['explorer.exe', str(folder)], shell=False)
                self._send(200, 'ok', 'text/plain')
            else:
                self._send(404, 'nope', 'text/plain')
        except PermissionError as e:
            self._send(403, str(e), 'text/plain')
        except UnsafeResumeError as e:
            self._send(409, str(e), 'text/plain')
        except Exception as e:
            self._send(500, f'err: {e}', 'text/plain')

if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    if AUTO_CLEAN_EMPTY_SESSIONS:
        try:
            removed = cleanup_empty_sessions()
            if removed:
                print(f'🧹 已彻底清理 {len(removed)} 个空白会话')
        except (sqlite3.Error, OSError) as error:
            print(f'⚠ 启动时清理空白会话失败: {error}', file=sys.stderr)
        start_empty_cleanup_worker()
    url = f'http://localhost:{PORT}/'
    print(f'🚀 Copilot 看板已启动: {url}')
    print('   Ctrl+C 停止服务')
    try: 
        if '--no-browser' not in sys.argv: webbrowser.open(url)
    except: pass
    try: ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
    except KeyboardInterrupt: print('\n已停止')
