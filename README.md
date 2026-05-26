# 🎵 TikTok Comments Scraper

A Streamlit web app for scraping, analysing, and exporting TikTok comments — powered by the [TikHub API](https://tikhub.io).

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)
![Streamlit](https://img.shields.io/badge/Streamlit-1.35+-red?logo=streamlit)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ Features

| Feature | Detail |
|---|---|
| 🔗 Multi-video input | Paste multiple video IDs or TikTok URLs (one per line) |
| 🔄 Auto ID resolution | Extracts the video ID automatically from any TikTok URL |
| 💬 Comments + replies | Fetches comments and all their replies in two steps |
| 📊 Sentiment analysis | Per-comment VADER sentiment score (Positive / Neutral / Negative) |
| 🔑 Keyword extraction | Top 20 keywords stripped of stop words |
| 📈 Per-video metrics | Comment count, total likes, reply count, sentiment breakdown |
| 📤 XLSX export | Timestamped workbook with three sheets: Comments, Replies, Summary |
| ⚙️ Sidebar controls | Adjustable comment count, min-likes filter, keyword filter |

---

## 🚀 Quick Start

### 1 — Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/tiktok-scraper.git
cd tiktok-scraper
```

### 2 — Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
```

### 3 — Install dependencies

```bash
pip install -r requirements.txt
```

### 4 — Run the app

```bash
streamlit run app.py
```

The app opens at **http://localhost:8501**.

---

## 🔑 API Key

This app uses the [TikHub API](https://tikhub.io).

1. Register at [tikhub.io](https://tikhub.io) and verify your email.
2. Go to **User Centre → API Token** and create a token.
3. Paste the token into the **🔑 TikHub API Key** field in the sidebar.

> Your key is never stored — it lives only in your browser session.

**Free trial:** After verifying your email, use the daily **Check-in** button in the TikHub dashboard to earn free credits (≈ 24 hrs cooldown).

---

## 📂 Project Structure

```
tiktok-scraper/
├── app.py                  # Main Streamlit application
├── requirements.txt        # Python dependencies
├── .gitignore
├── .streamlit/
│   └── config.toml         # Theme and server settings
└── README.md
```

---

## 📤 XLSX Export

The downloaded workbook contains three sheets:

| Sheet | Contents |
|---|---|
| **Comments** | All scraped comments with sentiment, likes, timestamps |
| **Replies** | Every reply linked back to its parent comment |
| **Summary** | Per-video totals — likes, sentiment %, top commenter |

Filenames are timestamped, e.g. `tiktok_comments_20260526_143022.xlsx`.

---

## ⚠️ Disclaimer

This tool is intended for personal research and analysis only.  
Please comply with [TikTok's Terms of Service](https://www.tiktok.com/legal/page/global/terms-of-service/en) and the [TikHub API Terms](https://tikhub.io) when using this application.

---

## 📄 License

MIT — see [LICENSE](LICENSE) for details.
