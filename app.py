"""
TikTok Comments Scraper
Powered by TikHub API — https://tikhub.io
"""

import streamlit as st
import requests
import time
import re
import io
from datetime import datetime
from collections import Counter

import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TikTok Comments Scraper",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
html, body, [data-testid="stAppViewContainer"] {
    background-color: #f7f8fc; color: #1a1a2e;
}
[data-testid="stSidebar"] {
    background-color: #ffffff;
    border-right: 1px solid #e8eaf0;
}
[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,[data-testid="stSidebar"] label,
[data-testid="stSidebar"] p { color: #1a1a2e !important; }
.metric-card {
    background:#fff; border:1.5px solid #e8eaf0;
    border-top:3px solid #e94560; border-radius:10px;
    padding:14px 16px; text-align:center;
    box-shadow:0 1px 4px rgba(0,0,0,.06);
}
.metric-card .value { font-size:1.8rem; font-weight:700; color:#e94560; }
.metric-card .label { font-size:.75rem; color:#6b7280; margin-top:4px;
    text-transform:uppercase; letter-spacing:.04em; }
.meta-card {
    background:#fff; border:1.5px solid #e8eaf0;
    border-left:4px solid #e94560; border-radius:10px;
    padding:18px 22px; box-shadow:0 1px 4px rgba(0,0,0,.06);
    margin-bottom:16px;
}
.meta-card h3 { margin:0 0 4px 0; color:#1a1a2e; font-size:1.1rem; }
.meta-row { display:flex; flex-wrap:wrap; gap:20px; margin-top:12px; }
.meta-item { display:flex; flex-direction:column; }
.meta-item .mi-label { font-size:.7rem; text-transform:uppercase;
    letter-spacing:.06em; color:#9ca3af; margin-bottom:2px; }
.meta-item .mi-value { font-size:.92rem; font-weight:500; color:#1a1a2e; }
h1,h2,h3 { color:#1a1a2e !important; }
.stDownloadButton > button {
    border-radius:8px !important; border:1.5px solid #e94560 !important;
    color:#e94560 !important; background:#fff !important; font-weight:500 !important;
}
.stDownloadButton > button:hover { background:#e94560 !important; color:#fff !important; }
.stButton > button[kind="primary"] {
    background:#e94560 !important; border:none !important;
    border-radius:8px !important; color:#fff !important; font-weight:600 !important;
}
.stButton > button[kind="primary"]:hover { background:#c73652 !important; }
[data-testid="stTabs"] button { color:#6b7280 !important; font-weight:500; }
[data-testid="stTabs"] button[aria-selected="true"] {
    color:#e94560 !important; border-bottom-color:#e94560 !important; }
.stProgress > div > div { background-color:#e94560 !important; }
</style>
""", unsafe_allow_html=True)

BASE_URL = "https://api.tikhub.io"


# ── Helpers ────────────────────────────────────────────────────────────────────
def make_headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}

def fmt_num(n) -> str:
    n = int(n or 0)
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000:     return f"{n/1_000:.1f}K"
    return str(n)

def fmt_time(unix_ts) -> str:
    if not unix_ts: return ""
    return datetime.fromtimestamp(int(unix_ts)).strftime("%Y-%m-%d %H:%M")

def fmt_duration(seconds) -> str:
    s = int(seconds or 0)
    return f"{s//60}m {s%60}s" if s >= 60 else f"{s}s"


# ── Video ID resolution ────────────────────────────────────────────────────────
def extract_video_id(value: str, headers: dict) -> str | None:
    value = value.strip()
    if value.isdigit():
        return value
    try:
        r = requests.get(f"{BASE_URL}/api/v1/tiktok/web/get_aweme_id",
                         headers=headers, params={"url": value}, timeout=20)
        if r.status_code == 200:
            vid = r.json().get("data", {}).get("aweme_id", "")
            if vid: return str(vid)
    except Exception:
        pass
    m = re.search(r"/video/(\d+)", value)
    return m.group(1) if m else None


# ── Video metadata ─────────────────────────────────────────────────────────────
def fetch_video_metadata(video_id: str, headers: dict) -> dict:
    raw = None
    for endpoint, param in [
        ("/api/v1/tiktok/web/fetch_post_detail",    "aweme_id"),
        ("/api/v1/tiktok/app/v3/fetch_one_video",   "aweme_id"),
    ]:
        try:
            r = requests.get(f"{BASE_URL}{endpoint}", headers=headers,
                             params={param: video_id}, timeout=30)
            if r.status_code == 200:
                body = r.json().get("data") or {}
                raw  = (body.get("aweme_detail")
                        or body.get("item_info", {}).get("itemStruct")
                        or body)
                if raw: break
        except Exception:
            pass
    if not raw:
        return {}
    author     = raw.get("author") or raw.get("authorMeta") or {}
    stats      = raw.get("statistics") or raw.get("stats") or {}
    music      = raw.get("music") or raw.get("musicMeta") or {}
    video_info = raw.get("video") or {}
    return {
        "video_id":        video_id,
        "title":           raw.get("desc") or raw.get("text") or "",
        "author":          author.get("unique_id") or author.get("uniqueId") or author.get("nickname",""),
        "author_name":     author.get("nickname") or "",
        "author_verified": bool(author.get("custom_verify") or author.get("verified")),
        "created_at":      fmt_time(raw.get("create_time") or raw.get("createTime") or 0),
        "duration":        fmt_duration(video_info.get("duration") or raw.get("duration") or 0),
        "views":           stats.get("play_count")    or stats.get("playCount")    or 0,
        "likes":           stats.get("digg_count")    or stats.get("diggCount")    or 0,
        "comments_count":  stats.get("comment_count") or stats.get("commentCount") or 0,
        "shares":          stats.get("share_count")   or stats.get("shareCount")   or 0,
        "bookmarks":       stats.get("collect_count") or stats.get("collectCount") or 0,
        "music_title":     music.get("title") or music.get("musicName") or "",
        "music_author":    music.get("author") or music.get("authorName") or "",
        "hashtags":        ", ".join(
            f"#{t.get('hashtagName') or t.get('title','')}"
            for t in (raw.get("text_extra") or raw.get("challenges") or [])
            if t.get("hashtagName") or t.get("title")
        ),
        "url": f"https://www.tiktok.com/@{author.get('unique_id','')}/video/{video_id}",
    }


# ── Fetch comments (paginated) ─────────────────────────────────────────────────
def fetch_comments(video_id: str, target: int, headers: dict,
                   progress_cb=None) -> list:
    comments, cursor = [], 0
    while len(comments) < target:
        count  = min(20, target - len(comments))
        params = {"aweme_id": video_id, "cursor": cursor,
                  "count": count, "current_region": ""}
        try:
            r = requests.get(f"{BASE_URL}/api/v1/tiktok/web/fetch_post_comment",
                             headers=headers, params=params, timeout=30)
        except Exception as e:
            st.error(f"Request error: {e}"); break
        if r.status_code == 401:
            st.error("❌ Invalid API key (401)."); break
        if r.status_code != 200:
            st.error(f"API error {r.status_code}: {r.text[:200]}"); break
        data  = r.json().get("data") or {}
        batch = data.get("comments") or []
        if not batch: break
        comments.extend(batch)
        cursor   = data.get("cursor", cursor + count)
        has_more = data.get("has_more", len(batch) == count)
        if progress_cb:
            progress_cb(min(len(comments) / target, 0.95))
        if not has_more: break
        if len(comments) < target: time.sleep(0.3)
    return comments[:target]


# ── Fetch replies — strictly per the API spec ──────────────────────────────────
# Endpoint : GET /api/v1/tiktok/web/fetch_post_comment_reply
# Required : item_id  (the VIDEO id, NOT aweme_id)
#            comment_id (the parent comment's cid)
# Optional : cursor, count, current_region
def fetch_replies_for_comment(item_id: str, comment_id: str,
                               headers: dict) -> list:
    """Paginate through ALL replies for one comment."""
    all_replies = []
    cursor      = 0

    while True:
        params = {
            "item_id":        item_id,    # ← spec says item_id
            "comment_id":     comment_id,
            "cursor":         cursor,
            "count":          20,
            "current_region": "",
        }
        try:
            r = requests.get(
                f"{BASE_URL}/api/v1/tiktok/web/fetch_post_comment_reply",
                headers=headers, params=params, timeout=30,
            )
        except Exception:
            break

        if r.status_code != 200:
            break

        data     = r.json().get("data") or {}
        batch    = data.get("comments") or []
        has_more = bool(data.get("has_more", False))
        cursor   = data.get("cursor", cursor + len(batch))

        if batch:
            all_replies.extend(batch)

        if not has_more or not batch:
            break

        time.sleep(0.25)

    return all_replies


def fetch_all_replies(item_id: str, parsed_comments: list,
                      headers: dict, progress_cb=None) -> None:
    """Attach replies list to every comment that has reply_count > 0."""
    eligible = [c for c in parsed_comments
                if c["reply_count"] > 0 and c["comment_id"]]
    total    = len(eligible)

    no_id = [c for c in parsed_comments
             if c["reply_count"] > 0 and not c["comment_id"]]
    if no_id:
        st.warning(f"⚠️ {len(no_id)} comment(s) have replies but no ID — skipped.")

    for i, c in enumerate(eligible):
        c["replies"] = fetch_replies_for_comment(item_id, c["comment_id"], headers)
        if progress_cb and total > 0:
            progress_cb((i + 1) / total)
        time.sleep(0.25)


# ── Parse raw comment dict ─────────────────────────────────────────────────────
def parse_comment(raw: dict, video_id: str) -> dict:
    user = raw.get("user") or {}
    # cid is the canonical comment ID field in TikTok Web API responses
    cid  = str(raw.get("cid") or raw.get("comment_id") or raw.get("id") or "").strip()
    return {
        "video_id":    video_id,
        "comment_id":  cid,
        "username":    user.get("unique_id") or user.get("nickname") or "",
        "text":        raw.get("text") or raw.get("comment_text") or "",
        "likes":       int(raw.get("digg_count") or 0),
        "reply_count": int(raw.get("reply_comment_total") or 0),
        "created_at":  fmt_time(raw.get("create_time") or raw.get("created_at")),
        "replies":     [],
    }


def parse_reply(raw: dict) -> dict:
    """Parse a raw reply dict into a flat dict."""
    user = raw.get("user") or {}
    return {
        "username": user.get("unique_id") or user.get("nickname") or "",
        "text":     raw.get("text") or raw.get("comment_text") or "",
        "likes":    int(raw.get("digg_count") or 0),
    }


# ── XLSX ───────────────────────────────────────────────────────────────────────
def build_xlsx(all_parsed: list, all_metadata: dict) -> bytes:
    wb = openpyxl.Workbook()

    hdr_font  = Font(bold=True, color="FFFFFF", size=11)
    hdr_fill  = PatternFill("solid", fgColor="E94560")
    center    = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left      = Alignment(horizontal="left",   vertical="center", wrap_text=True)
    thin      = Border(left=Side(style="thin"), right=Side(style="thin"),
                       top=Side(style="thin"),  bottom=Side(style="thin"))
    alt_fill  = PatternFill("solid", fgColor="FFF5F7")
    rep_fill  = PatternFill("solid", fgColor="FFF0F3")

    def style_header(ws, hdrs, widths):
        for ci, (h, w) in enumerate(zip(hdrs, widths), 1):
            cell = ws.cell(row=1, column=ci, value=h)
            cell.font = hdr_font; cell.fill = hdr_fill
            cell.alignment = center; cell.border = thin
            ws.column_dimensions[get_column_letter(ci)].width = w
        ws.row_dimensions[1].height = 22
        ws.freeze_panes = "A2"

    # ── Sheet 1 : Video Metadata ───────────────────────────────────────────────
    ws0 = wb.active
    ws0.title = "Video Metadata"
    style_header(ws0,
        ["Video ID","Title","Author","Display Name","Posted At","Duration",
         "Views","Likes","Comments","Shares","Bookmarks",
         "Music","Music Author","Hashtags","URL"],
        [22,50,20,25,18,10,14,14,12,12,12,30,25,40,50])
    for ri, (vid, m) in enumerate(all_metadata.items(), 2):
        vals = [m.get("video_id",""), m.get("title",""), m.get("author",""),
                m.get("author_name",""), m.get("created_at",""), m.get("duration",""),
                m.get("views",0), m.get("likes",0), m.get("comments_count",0),
                m.get("shares",0), m.get("bookmarks",0),
                m.get("music_title",""), m.get("music_author",""),
                m.get("hashtags",""), m.get("url","")]
        for ci, val in enumerate(vals, 1):
            cell = ws0.cell(row=ri, column=ci, value=val)
            cell.alignment = left if ci in (2,14,15) else center
            cell.border = thin
        ws0.row_dimensions[ri].height = 32

    # ── Sheet 2 : Comments & Replies (flat) ────────────────────────────────────
    ws1 = wb.create_sheet("Comments & Replies")
    style_header(ws1,
        ["#","Video ID","Type","Parent Username","Username","Text","Likes","Posted At"],
        [5, 22,         12,    22,               22,        65,    10,     18])

    row_num = 0
    xlsx_row = 2

    for c in all_parsed:
        row_num += 1
        fill = alt_fill if row_num % 2 == 0 else None

        # Comment row
        vals = [row_num, c["video_id"], "Comment", "",
                c["username"], c["text"], c["likes"], c["created_at"]]
        for ci, val in enumerate(vals, 1):
            cell = ws1.cell(row=xlsx_row, column=ci, value=val)
            cell.alignment = left if ci == 6 else center
            cell.border = thin
            if fill: cell.fill = fill
        ws1.row_dimensions[xlsx_row].height = 42
        xlsx_row += 1

        # Reply rows — one per reply, flat
        for rep_raw in c.get("replies") or []:
            row_num += 1
            rep = parse_reply(rep_raw)
            vals = [row_num, c["video_id"], "Reply", c["username"],
                    rep["username"], rep["text"], rep["likes"], ""]
            for ci, val in enumerate(vals, 1):
                cell = ws1.cell(row=xlsx_row, column=ci, value=val)
                cell.fill      = rep_fill
                cell.border    = thin
                cell.alignment = left if ci == 6 else center
            ws1.row_dimensions[xlsx_row].height = 42
            xlsx_row += 1

    # ── Sheet 3 : Summary ──────────────────────────────────────────────────────
    ws2 = wb.create_sheet("Summary")
    style_header(ws2,
        ["Video ID","Title","Author","Comments","Total Likes","Total Replies","Top Commenter"],
        [22,45,20,12,14,14,25])
    for ri, vid in enumerate(dict.fromkeys(c["video_id"] for c in all_parsed), 2):
        grp   = [c for c in all_parsed if c["video_id"] == vid]
        m     = all_metadata.get(vid, {})
        top_u = Counter(c["username"] for c in grp).most_common(1)
        vals  = [vid, (m.get("title","") or "")[:80], m.get("author",""),
                 len(grp), sum(c["likes"] for c in grp),
                 sum(len(c.get("replies") or []) for c in grp),
                 top_u[0][0] if top_u else ""]
        for ci, val in enumerate(vals, 1):
            cell = ws2.cell(row=ri, column=ci, value=val)
            cell.alignment = left if ci == 2 else center
            cell.border = thin
        ws2.row_dimensions[ri].height = 22

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ════════════════════════════════════════════════════════════════════════════════
#  UI
# ════════════════════════════════════════════════════════════════════════════════
st.title("🎵 TikTok Comments Scraper")
st.caption("Powered by [TikHub API](https://tikhub.io)")

with st.sidebar:
    st.header("⚙️ Settings")
    api_key = st.text_input("🔑 TikHub API Key", type="password",
                            placeholder="Paste your API key here…",
                            help="tikhub.io → User Centre → API Token")
    if api_key:
        st.success("API key set", icon="🔐")
    else:
        st.warning("Enter your API key to start.", icon="⚠️")

    st.divider()
    st.subheader("🎯 Scraping")
    num_comments = int(st.number_input("Max comments per video",
                                       min_value=10, value=50, step=10,
                                       help="No upper limit — large numbers take longer."))

    st.divider()
    st.subheader("🔍 Filters")
    min_likes      = st.number_input("Min likes on comment", min_value=0, value=0)
    keyword_filter = st.text_input("Keyword filter", placeholder="e.g. love")

    st.divider()
    st.caption("v1.0.0 · [TikHub Docs](https://docs.tikhub.io)")

st.subheader("📋 Video IDs / URLs")
st.caption("One TikTok video ID or URL per line.")
raw_input = st.text_area(label="videos", label_visibility="collapsed", height=140,
    placeholder="7611351401800748308\nhttps://www.tiktok.com/@user/video/123456789")
run_btn = st.button("▶  Start Scraping", type="primary", use_container_width=True)

if run_btn:
    if not api_key:
        st.error("Enter your API key in the sidebar first."); st.stop()
    lines = [l.strip() for l in raw_input.strip().splitlines() if l.strip()]
    if not lines:
        st.error("Enter at least one video ID or URL."); st.stop()

    headers:      dict = make_headers(api_key)
    all_parsed:   list = []
    all_metadata: dict = {}
    ts_str             = datetime.now().strftime("%Y%m%d_%H%M%S")

    for idx, line in enumerate(lines):
        st.markdown(f"---\n### 🎬 Video {idx+1} of {len(lines)}")
        st.code(line, language=None)

        # Resolve ID
        with st.spinner("Resolving video ID…"):
            video_id = extract_video_id(line, headers)
        if not video_id:
            st.error("Could not resolve a video ID."); continue
        st.caption(f"Video ID: **{video_id}**")

        # Metadata
        with st.spinner("Fetching video metadata…"):
            meta = fetch_video_metadata(video_id, headers)
        all_metadata[video_id] = meta
        if meta:
            verified = " ✅" if meta.get("author_verified") else ""
            st.markdown(
                f'<div class="meta-card"><h3>{meta.get("title","(no title)") or "(no title)"}</h3>'
                f'<div class="meta-row">'
                + "".join(
                    f'<div class="meta-item"><span class="mi-label">{lbl}</span>'
                    f'<span class="mi-value">{val}</span></div>'
                    for lbl, val in [
                        ("Author",       f'@{meta.get("author","")}{verified}'),
                        ("Display name", meta.get("author_name","")),
                        ("Posted",       meta.get("created_at","")),
                        ("Duration",     meta.get("duration","")),
                        ("Views",        fmt_num(meta.get("views",0))),
                        ("Likes",        fmt_num(meta.get("likes",0))),
                        ("Comments",     fmt_num(meta.get("comments_count",0))),
                        ("Shares",       fmt_num(meta.get("shares",0))),
                        ("Bookmarks",    fmt_num(meta.get("bookmarks",0))),
                        ("Music",        meta.get("music_title","") or "—"),
                    ]
                )
                + f'</div>'
                + (f'<div style="margin-top:10px;font-size:.82rem;color:#6b7280;">'
                   f'🏷 {meta["hashtags"]}</div>' if meta.get("hashtags") else "")
                + '</div>',
                unsafe_allow_html=True,
            )
        else:
            st.info("Metadata unavailable for this video.")

        # Step 1 — comments
        st.markdown("**Step 1 of 2 — Fetching comments**")
        prog1 = st.progress(0.0)
        raw   = fetch_comments(video_id, num_comments, headers,
                               progress_cb=lambda p: prog1.progress(p))
        prog1.progress(1.0, text=f"✅ {len(raw)} comments fetched")

        parsed = [parse_comment(c, video_id) for c in raw]

        # Filters
        filtered = parsed
        if min_likes > 0:
            filtered = [c for c in filtered if c["likes"] >= min_likes]
        if keyword_filter.strip():
            kw = keyword_filter.strip().lower()
            filtered = [c for c in filtered if kw in c["text"].lower()]

        # Step 2 — replies
        eligible = [c for c in filtered if c["reply_count"] > 0 and c["comment_id"]]
        if eligible:
            st.markdown(f"**Step 2 of 2 — Fetching replies** "
                        f"({len(eligible)} comment(s) have replies)")
            prog2 = st.progress(0.0)
            fetch_all_replies(video_id, filtered, headers,
                              progress_cb=lambda p: prog2.progress(p))
            total_replies = sum(len(c["replies"]) for c in filtered)
            prog2.progress(1.0, text=f"✅ {total_replies} replies fetched")
        else:
            st.markdown("**Step 2 of 2 — No replies for these comments**")

        all_parsed.extend(filtered)

        # Metrics
        n           = max(len(filtered), 1)
        total_likes = sum(c["likes"] for c in filtered)
        tot_rep     = sum(len(c.get("replies") or []) for c in filtered)

        st.write("")
        m1, m2, m3 = st.columns(3)
        for col, val, label in [
            (m1, len(filtered),        "Comments Scraped"),
            (m2, fmt_num(total_likes), "Total ❤ on Comments"),
            (m3, tot_rep,              "Replies Fetched"),
        ]:
            col.markdown(
                f'<div class="metric-card">'
                f'<div class="value">{val}</div>'
                f'<div class="label">{label}</div></div>',
                unsafe_allow_html=True)
        st.write("")

        # Tabs
        tab1, tab2 = st.tabs(["💬 Comments & Replies", "🔑 Top Keywords"])

        with tab1:
            rows = []
            for i, c in enumerate(filtered):
                rows.append({
                    "#":       i + 1,
                    "Type":    "Comment",
                    "Parent":  "",
                    "Username":c["username"],
                    "Text":    c["text"],
                    "Likes":   c["likes"],
                    "Posted":  c["created_at"],
                })
                for rep_raw in c.get("replies") or []:
                    rep = parse_reply(rep_raw)
                    rows.append({
                        "#":       "",
                        "Type":    "↳ Reply",
                        "Parent":  c["username"],
                        "Username":rep["username"],
                        "Text":    rep["text"],
                        "Likes":   rep["likes"],
                        "Posted":  "",
                    })
            st.dataframe(pd.DataFrame(rows), use_container_width=True,
                         hide_index=True,
                         column_config={
                             "#":        st.column_config.TextColumn(width="small"),
                             "Type":     st.column_config.TextColumn(width="small"),
                             "Parent":   st.column_config.TextColumn(width="medium"),
                             "Username": st.column_config.TextColumn(width="medium"),
                             "Text":     st.column_config.TextColumn(width="large"),
                             "Likes":    st.column_config.TextColumn(width="small"),
                             "Posted":   st.column_config.TextColumn(width="medium"),
                         })

        with tab2:
            try:
                from nltk.corpus import stopwords as _sw
                stop_words = set(_sw.words("english"))
            except Exception:
                stop_words = set()
            words = []
            for c in filtered:
                for w in re.findall(r"[a-zA-Z]{3,}", c["text"].lower()):
                    if w not in stop_words:
                        words.append(w)
            kws = Counter(words).most_common(20)
            if kws:
                kw_cols = st.columns(4)
                for i, (word, freq) in enumerate(kws):
                    kw_cols[i % 4].metric(word, freq)
            else:
                st.info("Not enough text to extract keywords.")

    # Export
    if all_parsed:
        st.markdown("---")
        st.subheader("📤 Export")
        with st.spinner("Building XLSX…"):
            xlsx_bytes = build_xlsx(all_parsed, all_metadata)
        fname = f"tiktok_comments_{ts_str}.xlsx"
        st.download_button(
            label=f"⬇  Download XLSX — {len(all_parsed)} rows · 3 sheets",
            data=xlsx_bytes,
            file_name=fname,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        st.caption(f"`{fname}` · Video Metadata · Comments & Replies · Summary")
