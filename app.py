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

import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from nltk.corpus import stopwords
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ── NLTK bootstrap (runs once per container) ──────────────────────────────────
for _pkg in ["vader_lexicon", "stopwords", "punkt", "punkt_tab"]:
    try:
        nltk.download(_pkg, quiet=True)
    except Exception:
        pass

# ── Streamlit page config ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="TikTok Comments Scraper",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.metric-card {
    background: #1a1a2e;
    border: 1px solid #16213e;
    border-radius: 12px;
    padding: 16px 20px;
    text-align: center;
}
.metric-card .value { font-size: 2rem; font-weight: 700; color: #e94560; }
.metric-card .label { font-size: 0.8rem; color: #aaa; margin-top: 4px; }
.comment-card {
    background: #0f3460;
    border-left: 3px solid #e94560;
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 10px;
}
.reply-card {
    background: #16213e;
    border-left: 3px solid #778ca3;
    border-radius: 6px;
    padding: 8px 14px;
    margin: 4px 0 4px 24px;
}
.sentiment-pos { color: #4caf50; font-weight: 600; }
.sentiment-neg { color: #f44336; font-weight: 600; }
.sentiment-neu { color: #9e9e9e; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
BASE_URL = "https://api.tikhub.io"

# ── Utility functions ─────────────────────────────────────────────────────────
def make_headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}


def fmt_num(n) -> str:
    n = int(n or 0)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def fmt_time(unix_ts) -> str:
    if not unix_ts:
        return ""
    return datetime.fromtimestamp(int(unix_ts)).strftime("%Y-%m-%d %H:%M")


def sentiment_label(score: float) -> str:
    if score >= 0.05:
        return "Positive"
    if score <= -0.05:
        return "Negative"
    return "Neutral"


def sentiment_cls(label: str) -> str:
    return {
        "Positive": "sentiment-pos",
        "Negative": "sentiment-neg",
        "Neutral":  "sentiment-neu",
    }[label]


def extract_keywords(texts: list, top_n: int = 20) -> list:
    stop_words: set = set()
    try:
        stop_words = set(stopwords.words("english"))
    except Exception:
        pass
    words = []
    for t in texts:
        for w in re.findall(r"[a-zA-Z]{3,}", t.lower()):
            if w not in stop_words:
                words.append(w)
    return Counter(words).most_common(top_n)


# ── Video ID resolution ───────────────────────────────────────────────────────
def extract_video_id(value: str, headers: dict) -> str | None:
    """Accept a raw video ID or any TikTok URL and return the numeric ID."""
    value = value.strip()
    if value.isdigit():
        return value
    # Try TikHub's dedicated extractor
    try:
        r = requests.get(
            f"{BASE_URL}/api/v1/tiktok/web/get_aweme_id",
            headers=headers,
            params={"url": value},
            timeout=20,
        )
        if r.status_code == 200:
            vid = r.json().get("data", {}).get("aweme_id", "")
            if vid:
                return vid
    except Exception:
        pass
    # Regex fallback for standard TikTok URLs
    m = re.search(r"/video/(\d+)", value)
    return m.group(1) if m else None


# ── API: fetch comments (paginated) ──────────────────────────────────────────
def fetch_comments(
    video_id: str,
    target: int,
    headers: dict,
    progress_cb=None,
) -> list:
    comments, cursor = [], 0
    while len(comments) < target:
        count = min(20, target - len(comments))
        params = {
            "aweme_id": video_id,
            "cursor": cursor,
            "count": count,
            "current_region": "",
        }
        try:
            r = requests.get(
                f"{BASE_URL}/api/v1/tiktok/web/fetch_post_comment",
                headers=headers,
                params=params,
                timeout=30,
            )
        except Exception as exc:
            st.error(f"Request error: {exc}")
            break
        if r.status_code == 401:
            st.error("❌ Invalid API key (401). Check the key in the sidebar.")
            break
        if r.status_code != 200:
            st.error(f"API error {r.status_code}: {r.text[:200]}")
            break
        data = r.json().get("data") or {}
        batch = data.get("comments") or data.get("data") or []
        if not batch:
            break
        comments.extend(batch)
        cursor = data.get("cursor", cursor + count)
        has_more = data.get("has_more", len(batch) == count)
        if progress_cb:
            progress_cb(min(len(comments) / target, 0.95))
        if not has_more:
            break
        if len(comments) < target:
            time.sleep(0.3)
    return comments[:target]


# ── API: fetch replies for every comment that has them ────────────────────────
def fetch_all_replies(
    video_id: str,
    parsed_comments: list,
    headers: dict,
    progress_cb=None,
) -> None:
    """Mutates parsed_comments in-place, adding a 'replies' list."""
    eligible = [c for c in parsed_comments if c["reply_count"] > 0 and c["comment_id"]]
    total = len(eligible)
    for i, c in enumerate(eligible):
        params = {
            "aweme_id": video_id,
            "comment_id": c["comment_id"],
            "cursor": 0,
            "count": 20,
            "current_region": "",
        }
        try:
            r = requests.get(
                f"{BASE_URL}/api/v1/tiktok/web/fetch_post_comment_reply",
                headers=headers,
                params=params,
                timeout=30,
            )
            if r.status_code == 200:
                c["replies"] = (r.json().get("data") or {}).get("comments") or []
        except Exception:
            pass
        if progress_cb and total > 0:
            progress_cb((i + 1) / total)
        time.sleep(0.2)


# ── Parse raw API comment dict into a flat dict ───────────────────────────────
def parse_comment(c: dict, video_id: str, sia=None) -> dict:
    user = c.get("user") or {}
    text = c.get("text") or c.get("comment_text", "")
    score = sia.polarity_scores(text)["compound"] if (sia and text) else 0.0
    return {
        "video_id":        video_id,
        "comment_id":      c.get("cid") or c.get("comment_id", ""),
        "username":        user.get("unique_id") or user.get("nickname", ""),
        "text":            text,
        "likes":           int(c.get("digg_count") or 0),
        "reply_count":     int(c.get("reply_comment_total") or 0),
        "created_at":      fmt_time(c.get("create_time") or c.get("created_at")),
        "sentiment_score": round(score, 4),
        "sentiment":       sentiment_label(score),
        "replies":         [],
    }


# ── Build XLSX workbook ───────────────────────────────────────────────────────
def build_xlsx(all_parsed: list) -> bytes:
    wb = openpyxl.Workbook()

    hdr_font = Font(bold=True, color="FFFFFF", size=11)
    hdr_fill = PatternFill("solid", fgColor="E94560")
    center   = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left     = Alignment(horizontal="left",   vertical="center", wrap_text=True)
    thin     = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"),  bottom=Side(style="thin"),
    )
    pos_fill = PatternFill("solid", fgColor="C8E6C9")
    neg_fill = PatternFill("solid", fgColor="FFCDD2")
    neu_fill = PatternFill("solid", fgColor="F5F5F5")

    def style_header(ws, headers, widths):
        for ci, (h, w) in enumerate(zip(headers, widths), 1):
            cell = ws.cell(row=1, column=ci, value=h)
            cell.font = hdr_font
            cell.fill = hdr_fill
            cell.alignment = center
            cell.border = thin
            ws.column_dimensions[get_column_letter(ci)].width = w
        ws.row_dimensions[1].height = 22
        ws.freeze_panes = "A2"

    # Sheet 1 — Comments
    ws1 = wb.active
    ws1.title = "Comments"
    style_header(
        ws1,
        ["#", "Video ID", "Username", "Comment",
         "Likes", "Replies", "Sentiment", "Score", "Posted At"],
        [5, 22, 20, 60, 10, 10, 12, 10, 18],
    )
    for i, c in enumerate(all_parsed, 1):
        fill = {"Positive": pos_fill, "Negative": neg_fill}.get(c["sentiment"], neu_fill)
        row  = [
            i, c["video_id"], c["username"], c["text"],
            c["likes"], c["reply_count"], c["sentiment"],
            c["sentiment_score"], c["created_at"],
        ]
        for ci, val in enumerate(row, 1):
            cell = ws1.cell(row=i + 1, column=ci, value=val)
            cell.alignment = left if ci == 4 else center
            cell.border = thin
            if ci == 7:
                cell.fill = fill
        ws1.row_dimensions[i + 1].height = 42

    # Sheet 2 — Replies
    ws2 = wb.create_sheet("Replies")
    style_header(
        ws2,
        ["Comment ID", "Video ID", "Commenter", "Original Comment",
         "Reply By", "Reply Text", "Reply Likes", "Sentiment", "Score"],
        [22, 20, 20, 45, 20, 50, 12, 12, 10],
    )
    _sia = None
    try:
        _sia = SentimentIntensityAnalyzer()
    except Exception:
        pass

    row_idx = 2
    for c in all_parsed:
        for rep in c.get("replies") or []:
            ru   = rep.get("user") or {}
            rtxt = rep.get("text", "")
            rs   = round(_sia.polarity_scores(rtxt)["compound"], 4) if (_sia and rtxt) else 0.0
            rl   = sentiment_label(rs)
            fill = {"Positive": pos_fill, "Negative": neg_fill}.get(rl, neu_fill)
            vals = [
                c["comment_id"], c["video_id"], c["username"], c["text"],
                ru.get("unique_id", ""), rtxt,
                int(rep.get("digg_count") or 0), rl, rs,
            ]
            for ci, val in enumerate(vals, 1):
                cell = ws2.cell(row=row_idx, column=ci, value=val)
                cell.alignment = left if ci in (4, 6) else center
                cell.border = thin
                if ci == 8:
                    cell.fill = fill
            ws2.row_dimensions[row_idx].height = 42
            row_idx += 1

    if row_idx == 2:
        ws2.cell(row=2, column=1, value="No replies fetched.").alignment = center

    # Sheet 3 — Per-video summary
    ws3 = wb.create_sheet("Summary")
    style_header(
        ws3,
        ["Video ID", "Comments", "Total Likes",
         "Positive %", "Negative %", "Neutral %",
         "Avg Sentiment", "Top Commenter"],
        [22, 12, 14, 14, 14, 14, 16, 25],
    )
    for ri, vid in enumerate(dict.fromkeys(c["video_id"] for c in all_parsed), 2):
        grp   = [c for c in all_parsed if c["video_id"] == vid]
        n     = len(grp)
        pos   = round(sum(1 for c in grp if c["sentiment"] == "Positive") / n * 100, 1)
        neg   = round(sum(1 for c in grp if c["sentiment"] == "Negative") / n * 100, 1)
        avg_s = round(sum(c["sentiment_score"] for c in grp) / n, 4)
        top_u = Counter(c["username"] for c in grp).most_common(1)
        vals  = [
            vid, n, sum(c["likes"] for c in grp),
            pos, neg, round(100 - pos - neg, 1),
            avg_s, top_u[0][0] if top_u else "",
        ]
        for ci, val in enumerate(vals, 1):
            cell = ws3.cell(row=ri, column=ci, value=val)
            cell.alignment = center
            cell.border = thin
        ws3.row_dimensions[ri].height = 22

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ════════════════════════════════════════════════════════════════════════════════
#  Streamlit UI
# ════════════════════════════════════════════════════════════════════════════════
st.title("🎵 TikTok Comments Scraper")
st.caption("Powered by [TikHub API](https://tikhub.io)")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")

    api_key = st.text_input(
        "🔑 TikHub API Key",
        type="password",
        placeholder="Paste your API key here…",
        help="Get yours at tikhub.io → User Centre → API Token",
    )
    if api_key:
        st.success("API key set", icon="🔐")
    else:
        st.warning("Enter your API key to start.", icon="⚠️")

    st.divider()
    st.subheader("🎯 Scraping")
    num_comments = st.slider("Comments per video", min_value=10, max_value=500,
                             value=50, step=10)

    st.divider()
    st.subheader("🔍 Filters")
    min_likes      = st.number_input("Min likes on comment", min_value=0, value=0)
    keyword_filter = st.text_input("Keyword filter", placeholder="e.g. love")

    st.divider()
    st.caption("v1.0.0 · [TikHub Docs](https://docs.tikhub.io)")

# ── Main panel ────────────────────────────────────────────────────────────────
st.subheader("📋 Video IDs / URLs")
st.caption("Paste one TikTok video ID or URL per line. Mixed input is supported.")
raw_input = st.text_area(
    label="videos",
    label_visibility="collapsed",
    height=140,
    placeholder=(
        "7611351401800748308\n"
        "https://www.tiktok.com/@user/video/123456789\n"
        "https://vm.tiktok.com/ZMxxxxxxxx/"
    ),
)

run_btn = st.button("▶  Start Scraping", type="primary", use_container_width=True)

# ── Run ───────────────────────────────────────────────────────────────────────
if run_btn:
    if not api_key:
        st.error("Please enter your TikHub API key in the sidebar first.")
        st.stop()

    lines = [l.strip() for l in raw_input.strip().splitlines() if l.strip()]
    if not lines:
        st.error("Enter at least one video ID or URL above.")
        st.stop()

    headers    = make_headers(api_key)
    all_parsed: list = []
    ts_str     = datetime.now().strftime("%Y%m%d_%H%M%S")

    sia = None
    try:
        sia = SentimentIntensityAnalyzer()
    except Exception:
        pass

    for idx, line in enumerate(lines):
        st.markdown(f"---\n### 🎬 Video {idx + 1} of {len(lines)}")
        st.code(line, language=None)

        # Step 0 — resolve ID
        with st.spinner("Resolving video ID…"):
            video_id = extract_video_id(line, headers)
        if not video_id:
            st.error(f"Could not resolve a video ID from the input above.")
            continue
        st.caption(f"Resolved video ID: **{video_id}**")

        # Step 1 — fetch comments
        st.markdown("**Step 1 of 2 — Fetching comments**")
        prog1 = st.progress(0.0)
        raw   = fetch_comments(
            video_id, num_comments, headers,
            progress_cb=lambda p: prog1.progress(p),
        )
        prog1.progress(1.0, text=f"✅ {len(raw)} comments fetched")

        parsed   = [parse_comment(c, video_id, sia) for c in raw]

        # Apply filters
        filtered = parsed
        if min_likes > 0:
            filtered = [c for c in filtered if c["likes"] >= min_likes]
        if keyword_filter.strip():
            kw = keyword_filter.strip().lower()
            filtered = [c for c in filtered if kw in c["text"].lower()]

        # Step 2 — fetch replies
        eligible = [c for c in filtered if c["reply_count"] > 0]
        if eligible:
            st.markdown(
                f"**Step 2 of 2 — Fetching replies** "
                f"({len(eligible)} comment(s) have replies)"
            )
            prog2 = st.progress(0.0)
            fetch_all_replies(
                video_id, filtered, headers,
                progress_cb=lambda p: prog2.progress(p),
            )
            total_replies = sum(len(c["replies"]) for c in filtered)
            prog2.progress(1.0, text=f"✅ {total_replies} replies fetched")
        else:
            st.markdown("**Step 2 of 2 — No replies found for these comments**")

        all_parsed.extend(filtered)

        # Metrics row
        n           = max(len(filtered), 1)
        total_likes = sum(c["likes"] for c in filtered)
        pos_pct     = round(sum(1 for c in filtered if c["sentiment"] == "Positive") / n * 100)
        neg_pct     = round(sum(1 for c in filtered if c["sentiment"] == "Negative") / n * 100)
        neu_pct     = 100 - pos_pct - neg_pct
        tot_rep     = sum(len(c["replies"]) for c in filtered)

        st.write("")
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        for col, val, label in [
            (m1, len(filtered),        "Comments"),
            (m2, fmt_num(total_likes), "Total ❤"),
            (m3, tot_rep,              "Replies"),
            (m4, f"{pos_pct}%",        "😊 Positive"),
            (m5, f"{neg_pct}%",        "😠 Negative"),
            (m6, f"{neu_pct}%",        "😐 Neutral"),
        ]:
            col.markdown(
                f'<div class="metric-card">'
                f'<div class="value">{val}</div>'
                f'<div class="label">{label}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        st.write("")

        # Tabs
        tab1, tab2, tab3 = st.tabs(
            ["💬 Comments & Replies", "🔑 Top Keywords", "📊 Sentiment"]
        )

        with tab1:
            for ci, c in enumerate(filtered):
                sc = sentiment_cls(c["sentiment"])
                st.markdown(
                    f'<div class="comment-card">'
                    f'<strong>@{c["username"]}</strong>'
                    f'&nbsp;<span class="{sc}">{c["sentiment"]}</span>'
                    f'&nbsp;·&nbsp;❤ {fmt_num(c["likes"])}'
                    f'&nbsp;·&nbsp;💬 {c["reply_count"]}'
                    f'&nbsp;·&nbsp;{c["created_at"]}'
                    f'<br>{c["text"]}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                for rep in c.get("replies") or []:
                    ru   = rep.get("user") or {}
                    rtxt = rep.get("text", "")
                    rl   = int(rep.get("digg_count") or 0)
                    st.markdown(
                        f'<div class="reply-card">'
                        f'└ <strong>@{ru.get("unique_id", "?")}</strong>'
                        f'&nbsp;·&nbsp;❤ {fmt_num(rl)}'
                        f'<br>{rtxt}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                # ── Per-row TXT export button ──────────────────────────────
                reply_lines = ""
                for rep in c.get("replies") or []:
                    ru   = rep.get("user") or {}
                    rtxt = rep.get("text", "")
                    rl   = int(rep.get("digg_count") or 0)
                    reply_lines += (
                        f"  └ @{ru.get('unique_id','?')}: {rtxt}  (❤ {rl})\n"
                    )
                txt_content = (
                    f"═══════════════════════════════════════\n"
                    f"Video ID  : {c['video_id']}\n"
                    f"Username  : @{c['username']}\n"
                    f"Posted    : {c['created_at']}\n"
                    f"Likes     : {c['likes']}\n"
                    f"Replies   : {c['reply_count']}\n"
                    f"Sentiment : {c['sentiment']} ({c['sentiment_score']:+.4f})\n"
                    f"═══════════════════════════════════════\n"
                    f"\nComment:\n{c['text']}\n"
                    + (f"\nReplies:\n{reply_lines}" if reply_lines else "")
                )
                safe_user = re.sub(r"[^\w]", "_", c["username"])[:20]
                st.download_button(
                    label="📄 Export as TXT",
                    data=txt_content.encode("utf-8"),
                    file_name=f"comment_{safe_user}_{ci + 1}.txt",
                    mime="text/plain",
                    key=f"txt_{video_id}_{ci}",
                )

        with tab2:
            kws = extract_keywords([c["text"] for c in filtered], top_n=20)
            if kws:
                kw_cols = st.columns(4)
                for i, (word, freq) in enumerate(kws):
                    kw_cols[i % 4].metric(word, freq)
            else:
                st.info("Not enough text to extract keywords.")

        with tab3:
            pos = sum(1 for c in filtered if c["sentiment"] == "Positive")
            neg = sum(1 for c in filtered if c["sentiment"] == "Negative")
            neu = len(filtered) - pos - neg
            st.bar_chart({"Positive": pos, "Negative": neg, "Neutral": neu})
            avg_s = sum(c["sentiment_score"] for c in filtered) / n
            st.metric(
                "Average sentiment score",
                f"{avg_s:.4f}",
                help="+1.0 = very positive · −1.0 = very negative",
            )

    # ── Export ────────────────────────────────────────────────────────────────
    if all_parsed:
        st.markdown("---")
        st.subheader("📤 Export")

        ecol1, ecol2 = st.columns(2)

        # XLSX
        with ecol1:
            with st.spinner("Building XLSX…"):
                xlsx_bytes = build_xlsx(all_parsed)
            fname_xlsx = f"tiktok_comments_{ts_str}.xlsx"
            st.download_button(
                label=f"⬇  Download XLSX — {len(all_parsed)} comments · 3 sheets",
                data=xlsx_bytes,
                file_name=fname_xlsx,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
            st.caption(f"`{fname_xlsx}` · Comments · Replies · Summary")

        # Bulk TXT — all comments in one file
        with ecol2:
            txt_lines = []
            for i, c in enumerate(all_parsed, 1):
                reply_lines = ""
                for rep in c.get("replies") or []:
                    ru   = rep.get("user") or {}
                    rtxt = rep.get("text", "")
                    rl   = int(rep.get("digg_count") or 0)
                    reply_lines += f"  └ @{ru.get('unique_id','?')}: {rtxt}  (❤ {rl})\n"
                txt_lines.append(
                    f"{'═'*45}\n"
                    f"[{i}] @{c['username']}  ·  {c['created_at']}\n"
                    f"Video     : {c['video_id']}\n"
                    f"Likes     : {c['likes']}   Replies: {c['reply_count']}\n"
                    f"Sentiment : {c['sentiment']} ({c['sentiment_score']:+.4f})\n"
                    f"{'─'*45}\n"
                    f"{c['text']}\n"
                    + (f"\nReplies:\n{reply_lines}" if reply_lines else "")
                )
            bulk_txt = "\n".join(txt_lines)
            fname_txt = f"tiktok_comments_{ts_str}.txt"
            st.download_button(
                label=f"⬇  Download All as TXT — {len(all_parsed)} comments",
                data=bulk_txt.encode("utf-8"),
                file_name=fname_txt,
                mime="text/plain",
                use_container_width=True,
            )
            st.caption(f"`{fname_txt}` · All comments + replies in plain text")
