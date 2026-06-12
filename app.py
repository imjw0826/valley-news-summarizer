"""핸드폰에서 쓰는 시황뉴스 요약 웹 앱.

맥에서 `python app.py`로 실행해 두고, 같은 와이파이에 연결된 핸드폰 브라우저에서
http://<맥의 IP>:8765 로 접속하면 버튼 한 번으로 요약을 생성하고 읽을 수 있다.
"""

import socket
import threading
import traceback

import markdown as md
from flask import Flask, redirect, render_template_string, request, abort

from valley_news import OUTPUT_DIR, SUMMARIZERS, run_pipeline

app = Flask(__name__)

state = {"running": False, "log": [], "error": None}


def _progress(msg: str) -> None:
    print(msg, flush=True)
    state["log"].append(msg)


def _worker(days: int, provider: str) -> None:
    try:
        run_pipeline(days=days, provider=provider, progress=_progress)
    except Exception as e:
        state["error"] = str(e)
        traceback.print_exc()
    finally:
        state["running"] = False


PAGE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>시황뉴스 요약</title>
{% if state.running %}<meta http-equiv="refresh" content="5">{% endif %}
<style>
  body { font-family: -apple-system, "Apple SD Gothic Neo", sans-serif; margin: 0;
         background: #f5f5f7; color: #1d1d1f; }
  .wrap { max-width: 640px; margin: 0 auto; padding: 16px; }
  h1 { font-size: 1.3rem; }
  .card { background: #fff; border-radius: 12px; padding: 16px; margin-bottom: 12px;
          box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  select, button { font-size: 1rem; padding: 10px 14px; border-radius: 8px;
                   border: 1px solid #d2d2d7; }
  button { background: #0071e3; color: #fff; border: none; width: 100%; margin-top: 10px; }
  button:disabled { background: #999; }
  .row { display: flex; gap: 8px; }
  .row select { flex: 1; }
  a.file { display: block; padding: 12px 4px; border-bottom: 1px solid #eee;
           text-decoration: none; color: #0071e3; }
  .log { font-size: .8rem; color: #555; white-space: pre-wrap; max-height: 200px;
         overflow-y: auto; background: #fafafa; border-radius: 8px; padding: 8px; }
  .error { color: #d70015; }
</style>
</head>
<body><div class="wrap">
<h1>📰 Valley 시황뉴스 요약</h1>

<div class="card">
  <form method="post" action="/generate">
    <div class="row">
      <select name="days">
        <option value="1">최근 1일</option>
        <option value="3">최근 3일</option>
        <option value="7" selected>최근 7일</option>
        <option value="14">최근 14일</option>
      </select>
      <select name="provider">
        {% for p in providers %}<option value="{{p}}">{{p}}</option>{% endfor %}
      </select>
    </div>
    <button type="submit" {% if state.running %}disabled{% endif %}>
      {% if state.running %}생성 중... (자동 새로고침){% else %}요약 생성{% endif %}
    </button>
  </form>
  {% if state.error %}<p class="error">⚠ {{ state.error }}</p>{% endif %}
  {% if state.log %}<div class="log">{{ state.log | join('\n') }}</div>{% endif %}
</div>

<div class="card">
  <h2 style="font-size:1.05rem">생성된 문서</h2>
  {% for f in files %}<a class="file" href="/view/{{ f }}">{{ f }}</a>
  {% else %}<p style="color:#888">아직 없습니다.</p>{% endfor %}
</div>
</div></body></html>"""

VIEW = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ name }}</title>
<style>
  body { font-family: -apple-system, "Apple SD Gothic Neo", sans-serif; margin: 0;
         background: #fff; color: #1d1d1f; line-height: 1.65; }
  .wrap { max-width: 680px; margin: 0 auto; padding: 16px 20px 60px; }
  h1 { font-size: 1.4rem; } h2 { font-size: 1.15rem; margin-top: 1.6em; }
  a { color: #0071e3; word-break: break-all; }
  li { margin-bottom: .35em; }
  .back { display: inline-block; margin-bottom: 12px; }
</style>
</head>
<body><div class="wrap">
<a class="back" href="/">← 목록으로</a>
{{ body | safe }}
</div></body></html>"""


@app.route("/")
def index():
    OUTPUT_DIR.mkdir(exist_ok=True)
    files = sorted((f.name for f in OUTPUT_DIR.glob("*.md")), reverse=True)
    return render_template_string(
        PAGE, state=state, files=files, providers=list(SUMMARIZERS)
    )


@app.post("/generate")
def generate():
    if not state["running"]:
        state.update(running=True, log=[], error=None)
        days = int(request.form.get("days", 7))
        provider = request.form.get("provider", "deepseek")
        threading.Thread(target=_worker, args=(days, provider), daemon=True).start()
    return redirect("/")


@app.route("/view/<name>")
def view(name):
    path = OUTPUT_DIR / name
    if "/" in name or not name.endswith(".md") or not path.exists():
        abort(404)
    body = md.markdown(path.read_text(encoding="utf-8"), extensions=["tables"])
    return render_template_string(VIEW, name=name, body=body)


def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    ip = local_ip()
    print(f"\n📱 핸드폰에서 접속: http://{ip}:8765  (같은 와이파이에 연결되어 있어야 함)\n")
    app.run(host="0.0.0.0", port=8765)
