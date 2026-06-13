"""Read-only FastAPI dashboard over the pipeline.

Routes:
    GET /                 overview (headline counts + recent posts/logs)
    GET /trends           all trends, ranked
    GET /trends/{id}      one trend with its scripts
    GET /videos           all videos + QA/status
    GET /posts            published videos
    GET /logs             recent pipeline_logs (?level=error to filter)
    GET /api/stats        overview counts as JSON

Run:
    python -m dashboard.app          (serves on http://127.0.0.1:8000)
"""

from __future__ import annotations

import html

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from dashboard import queries

app = FastAPI(title="AI Video Pipeline Dashboard")

_STYLE = """
<style>
  :root { color-scheme: light dark; }
  body { font-family: system-ui, sans-serif; margin: 0; background: #0f1115; color: #e6e6e6; }
  header { background: #171a21; padding: 14px 22px; border-bottom: 1px solid #2a2f3a; }
  header a { color: #9ec1ff; text-decoration: none; margin-right: 18px; font-weight: 600; }
  header a:hover { color: #fff; }
  main { padding: 22px; max-width: 1100px; margin: 0 auto; }
  h1 { font-size: 20px; margin: 0 0 16px; }
  h2 { font-size: 16px; margin: 24px 0 10px; color: #b9c2d0; }
  .cards { display: flex; flex-wrap: wrap; gap: 12px; }
  .card { background: #171a21; border: 1px solid #2a2f3a; border-radius: 10px;
          padding: 14px 18px; min-width: 120px; }
  .card .n { font-size: 26px; font-weight: 700; }
  .card .l { font-size: 12px; color: #8a93a3; text-transform: uppercase; letter-spacing: .04em; }
  table { border-collapse: collapse; width: 100%; margin-top: 8px; font-size: 14px; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #232833; }
  th { color: #8a93a3; font-weight: 600; }
  tr:hover td { background: #161922; }
  a.link { color: #9ec1ff; text-decoration: none; }
  a.link:hover { text-decoration: underline; }
  .tag { display: inline-block; padding: 2px 8px; border-radius: 99px; font-size: 12px;
         background: #232833; color: #b9c2d0; }
  .ok { background: #14361f; color: #7ee2a8; }
  .bad { background: #3a1620; color: #ff9aa9; }
  .muted { color: #6b7280; }
  .lvl-error { color: #ff9aa9; }
  .lvl-warning { color: #ffd479; }
  .score { font-variant-numeric: tabular-nums; }
</style>
"""

_NAV = """
<header>
  <a href="/">Overview</a>
  <a href="/trends">Trends</a>
  <a href="/videos">Videos</a>
  <a href="/posts">Posts</a>
  <a href="/logs">Logs</a>
</header>
"""


def _page(title: str, body: str) -> str:
    return (
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{html.escape(title)}</title>{_STYLE}</head>"
        f"<body>{_NAV}<main>{body}</main></body></html>"
    )


def _esc(v) -> str:
    return html.escape("" if v is None else str(v))


def _status_tag(status: str) -> str:
    cls = "tag"
    if status in ("posted", "qa_passed", "selected", "completed"):
        cls = "tag ok"
    elif status in ("failed", "qa_failed", "rejected", "expired"):
        cls = "tag bad"
    return f"<span class='{cls}'>{_esc(status)}</span>"


def _score(v) -> str:
    return "—" if v is None else f"<span class='score'>{float(v):.1f}</span>"


@app.get("/", response_class=HTMLResponse)
def overview() -> str:
    s = queries.overview_stats()
    cards = [
        ("Raw trends", s["raw_trends"]),
        ("Trends", s["trends"]),
        ("AI trends", s["ai_trends"]),
        ("Scripts", s["scripts"]),
        ("Selected", s["scripts_selected"]),
        ("Videos", s["videos"]),
        ("QA passed", s["videos_qa_passed"]),
        ("Posted", s["posts"]),
        ("Errors", s["errors"]),
    ]
    card_html = "".join(
        f"<div class='card'><div class='n'>{n}</div><div class='l'>{_esc(label)}</div></div>"
        for label, n in cards
    )

    posts = queries.list_posts(limit=5)
    post_rows = "".join(
        f"<tr><td>{_status_tag(p['status'])}</td>"
        f"<td>{_esc(p['title'])}</td>"
        f"<td>{_link(p['post_url'])}</td></tr>"
        for p in posts
    ) or "<tr><td colspan=3 class='muted'>No posts yet</td></tr>"

    logs = queries.list_logs(limit=10)
    log_rows = "".join(_log_row(lg) for lg in logs) or "<tr><td colspan=3>No logs</td></tr>"

    body = (
        "<h1>Pipeline Overview</h1>"
        f"<div class='cards'>{card_html}</div>"
        "<h2>Recent posts</h2>"
        f"<table><tr><th>Status</th><th>Title</th><th>Link</th></tr>{post_rows}</table>"
        "<h2>Recent activity</h2>"
        f"<table><tr><th>Time</th><th>Module</th><th>Message</th></tr>{log_rows}</table>"
    )
    return _page("Overview", body)


@app.get("/trends", response_class=HTMLResponse)
def trends() -> str:
    rows = queries.list_trends()
    body_rows = "".join(
        f"<tr><td><a class='link' href='/trends/{t['id']}'>{_esc(t['name'])}</a></td>"
        f"<td>{_esc(t['category'])}</td>"
        f"<td>{'yes' if t['is_ai_trend'] else 'no'}</td>"
        f"<td>{_score(t['overall_score'])}</td>"
        f"<td>{_score(t['momentum_score'])}</td>"
        f"<td>{_score(t['saturation_score'])}</td>"
        f"<td>{_score(t['fit_score'])}</td>"
        f"<td>{_status_tag(t['status'])}</td>"
        f"<td>{t['n_scripts']}</td></tr>"
        for t in rows
    ) or "<tr><td colspan=9 class='muted'>No trends yet</td></tr>"
    body = (
        "<h1>Trends</h1>"
        "<table><tr><th>Name</th><th>Category</th><th>AI?</th><th>Overall</th>"
        "<th>Momentum</th><th>Saturation</th><th>Fit</th><th>Status</th><th>Scripts</th></tr>"
        f"{body_rows}</table>"
    )
    return _page("Trends", body)


@app.get("/trends/{trend_id}", response_class=HTMLResponse)
def trend_detail(trend_id: int) -> HTMLResponse:
    t = queries.trend_detail(trend_id)
    if t is None:
        return HTMLResponse(_page("Not found", "<h1>Trend not found</h1>"), status_code=404)
    script_rows = "".join(
        f"<tr><td>{_esc(s['selection_rank'] or '')}</td>"
        f"<td>{_esc(s['title'])}</td>"
        f"<td>{_esc(s['premise'])}</td>"
        f"<td>{_status_tag(s['status'])}</td>"
        f"<td>{_score(s['quality_score'])}</td>"
        f"<td>{s['n_videos']}</td></tr>"
        for s in t["scripts"]
    ) or "<tr><td colspan=6 class='muted'>No scripts yet</td></tr>"
    body = (
        f"<h1>{_esc(t['name'])} {_status_tag(t['status'])}</h1>"
        f"<p class='muted'>{_esc(t['summary'])}</p>"
        f"<p>Category: {_esc(t['category'])} · Overall score: {_score(t['overall_score'])}</p>"
        "<h2>Scripts</h2>"
        "<table><tr><th>Rank</th><th>Title</th><th>Premise</th><th>Status</th>"
        f"<th>Quality</th><th>Videos</th></tr>{script_rows}</table>"
    )
    return HTMLResponse(_page(t["name"], body))


@app.get("/videos", response_class=HTMLResponse)
def videos() -> str:
    rows = queries.list_videos()
    body_rows = "".join(
        f"<tr><td>{v['id']}</td><td>{v['script_id']}</td><td>{_esc(v['provider'])}</td>"
        f"<td>{_status_tag(v['status'])}</td>"
        f"<td>{_esc(v['duration_seconds'])}</td>"
        f"<td>{_link(v['video_url'])}</td>"
        f"<td class='muted'>{_esc((v['qa_notes'] or '')[:80])}</td></tr>"
        for v in rows
    ) or "<tr><td colspan=7 class='muted'>No videos yet</td></tr>"
    body = (
        "<h1>Videos</h1>"
        "<table><tr><th>ID</th><th>Script</th><th>Provider</th><th>Status</th>"
        f"<th>Dur</th><th>URL</th><th>QA</th></tr>{body_rows}</table>"
    )
    return _page("Videos", body)


@app.get("/posts", response_class=HTMLResponse)
def posts() -> str:
    rows = queries.list_posts()
    body_rows = "".join(
        f"<tr><td>{_status_tag(p['status'])}</td>"
        f"<td>{_esc(p['title'])}</td>"
        f"<td>{_esc(p['privacy'])}</td>"
        f"<td>{_link(p['post_url'])}</td>"
        f"<td class='muted'>{_esc(p['posted_at'])}</td></tr>"
        for p in rows
    ) or "<tr><td colspan=5 class='muted'>No posts yet</td></tr>"
    body = (
        "<h1>Posts</h1>"
        "<table><tr><th>Status</th><th>Title</th><th>Privacy</th><th>Link</th>"
        f"<th>Posted</th></tr>{body_rows}</table>"
    )
    return _page("Posts", body)


@app.get("/logs", response_class=HTMLResponse)
def logs(level: str | None = None) -> str:
    rows = queries.list_logs(level=level)
    body_rows = "".join(_log_row(lg) for lg in rows) or "<tr><td colspan=3>No logs</td></tr>"
    body = (
        "<h1>Logs</h1>"
        "<p><a class='link' href='/logs'>all</a> · "
        "<a class='link' href='/logs?level=error'>errors</a> · "
        "<a class='link' href='/logs?level=warning'>warnings</a></p>"
        f"<table><tr><th>Time</th><th>Module</th><th>Message</th></tr>{body_rows}</table>"
    )
    return _page("Logs", body)


@app.get("/api/stats")
def api_stats() -> JSONResponse:
    return JSONResponse(queries.overview_stats())


def _link(url: str | None) -> str:
    if not url:
        return "<span class='muted'>—</span>"
    return f"<a class='link' href='{_esc(url)}' target='_blank'>open</a>"


def _log_row(lg: dict) -> str:
    lvl_class = f"lvl-{lg['level']}"
    ts = (lg["timestamp"] or "")[:19].replace("T", " ")
    return (
        f"<tr><td class='muted'>{_esc(ts)}</td>"
        f"<td>{_esc(lg['module'])}</td>"
        f"<td class='{lvl_class}'>{_esc(lg['message'])}</td></tr>"
    )


def main() -> None:
    import uvicorn

    from db.init import init_db

    init_db()
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
