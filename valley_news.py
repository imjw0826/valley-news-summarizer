"""Valley.town 시황뉴스 자동 요약기.

흐름:
1. Playwright로 valley.town에 로그인 (세션은 auth_state.json에 저장돼 재사용)
2. 월가아재 시황칼럼 > 오늘의 핵심뉴스 피드에서 최근 N일치 게시물 수집 (스크롤 포함)
3. DeepSeek 또는 Claude API로 요약
4. output/ 폴더에 마크다운 문서 생성

사용법:
    python valley_news.py                          # 최근 7일치, DeepSeek으로 요약
    python valley_news.py --days 3
    python valley_news.py --provider claude        # Claude API 사용
    python valley_news.py --headed                 # 브라우저 창을 띄워서 디버깅
"""

import argparse
import datetime as dt
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.valley.town"
NEWS_URL = f"{BASE_URL}/premium/wsaj-column/daily-news"
PROJECT_DIR = Path(__file__).parent
AUTH_STATE = PROJECT_DIR / "auth_state.json"
OUTPUT_DIR = PROJECT_DIR / "output"

load_dotenv(PROJECT_DIR / ".env")

MAX_CHARS_PER_POST = 10000  # 게시물당 LLM에 보낼 본문 최대 길이

SUMMARY_SYSTEM_PROMPT = """\
당신은 금융 시장 전문 애널리스트입니다. valley.town의 '월가아재 시황칼럼 - 오늘의 핵심뉴스' \
게시물들을 받아, 투자자가 10분 안에 읽을 수 있는 기간 시황 브리핑 문서를 작성합니다. \
여러 날짜의 게시물이 주어지면 날짜별 나열이 아니라 기간 전체의 흐름과 테마 중심으로 종합합니다.

출력 형식 (마크다운):
# 📰 시황 브리핑 — {기간}

## 🔑 핵심 요약 (5줄 이내)
이 기간 시장을 관통한 가장 중요한 흐름.

## 🌍 정치·거시경제
주요 테마별로 소제목을 달고 불릿으로 정리. 시장에 미치는 함의를 덧붙임.

## 🏭 산업·기업
주요 기업/산업 뉴스를 테마별로 정리. 주가에 큰 영향을 준 뉴스는 변동폭 명시.

## 📈 기간 중 시장 흐름
기간 동안 시장 분위기가 어떻게 변해왔는지 서술 (예: 초반 위험회피 → 후반 반등).

## 💡 투자 시사점
위 뉴스들을 종합해 투자자가 주목할 포인트 3~5가지.

규칙:
- 원문에 없는 사실을 지어내지 않는다.
- 숫자(주가 변동률, 금리 등)는 원문 그대로 정확히 옮긴다.
- 같은 사건의 후속 보도는 흐름으로 묶어서 정리한다.
"""


def log(msg: str) -> None:
    print(f"[valley-news] {msg}", flush=True)


# ---------------------------------------------------------------- 로그인


def login(page, email: str, password: str) -> None:
    """이메일/비밀번호로 로그인한다."""
    log("로그인 시도 중...")
    page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
    page.fill('input[name="email"]', email)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    try:
        page.wait_for_url(lambda url: "/login" not in url, timeout=15000)
    except PlaywrightTimeout:
        raise RuntimeError(
            "로그인에 실패했습니다. .env의 VALLEY_EMAIL / VALLEY_PASSWORD를 확인하세요."
        )
    log("로그인 성공")


def is_logged_in(page) -> bool:
    page.goto(NEWS_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    # 로그인 상태면 헤더에 '로그인' 링크가 없다
    return page.locator('a[href^="/login"]').count() == 0


# ---------------------------------------------------------------- 수집


def _parse_cards(page) -> list[dict]:
    cards = page.eval_on_selector_all(
        'a[href*="/daily-news/"]',
        """els => els
            .filter(a => /\\/daily-news\\/[a-f0-9]{20,}/.test(a.getAttribute('href')))
            .map(a => ({ href: a.getAttribute('href'), text: a.innerText.trim() }))
        """,
    )
    parsed = []
    for c in cards:
        m = re.search(r"(\d{4})[.\s]+(\d{2})[.\s]+(\d{2})", c["text"])
        date = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
        title = next(
            (ln.strip() for ln in c["text"].splitlines() if ln.strip().startswith("[")),
            c["text"].splitlines()[0].strip() if c["text"] else c["href"],
        )
        parsed.append({"href": c["href"], "title": title, "date": date})
    return parsed


def collect_posts(page, days: int, max_posts: int) -> tuple[list[dict], str]:
    """피드를 스크롤하며 최근 N일치 게시물을 모으고 본문을 가져온다."""
    cutoff = dt.date.today() - dt.timedelta(days=days)
    page.goto(NEWS_URL, wait_until="domcontentloaded")
    page.wait_for_selector('a[href*="/daily-news/"]', timeout=15000)

    # 무한 스크롤: cutoff 이전 게시물이 보일 때까지 내려간다
    stall = 0
    for _ in range(30):
        cards = _parse_cards(page)
        dated = [c["date"] for c in cards if c["date"]]
        if dated and min(dated) < cutoff:
            break
        prev = len(cards)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1500)
        if len(_parse_cards(page)) == prev:
            # 스크롤로 안 늘어나면 '더보기' 버튼 시도
            btn = page.locator('button:has-text("더보기")')
            if btn.count():
                btn.first.click()
                page.wait_for_timeout(1500)
            else:
                stall += 1
                if stall >= 2:
                    break
        else:
            stall = 0

    cards = _parse_cards(page)
    seen, posts = set(), []
    for c in cards:
        if c["href"] in seen or not c["date"]:
            continue
        seen.add(c["href"])
        if c["date"] >= cutoff:
            posts.append(
                {"url": BASE_URL + c["href"], "title": c["title"], "date": c["date"]}
            )

    if not posts:
        raise RuntimeError(
            f"최근 {days}일({cutoff} 이후) 게시물을 찾지 못했습니다. "
            "사이트 구조가 바뀌었을 수 있습니다."
        )

    posts.sort(key=lambda p: p["date"])  # 오래된 것부터 (흐름 파악용)
    posts = posts[-max_posts:]
    period = f"{posts[0]['date']:%Y-%m-%d} ~ {posts[-1]['date']:%Y-%m-%d}"
    log(f"{period} 게시물 {len(posts)}건 본문 수집 시작")

    for p in posts:
        log(f"  - [{p['date']}] {p['title'][:50]}")
        page.goto(p["url"], wait_until="domcontentloaded")
        page.wait_for_timeout(2500)  # 클라이언트 렌더링 대기
        for selector in ("main", "article", "body"):
            try:
                text = page.locator(selector).first.inner_text(timeout=5000)
                if len(text.strip()) > 200:
                    p["content"] = text.strip()
                    break
            except Exception:
                continue
        if not p.get("content"):
            log(f"    ⚠ 본문 추출 실패: {p['url']}")

    return [p for p in posts if p.get("content")], period


# ---------------------------------------------------------------- 요약


def _build_user_message(posts: list[dict], period: str) -> str:
    articles = "\n\n".join(
        f"<article>\n<date>{p['date']}</date>\n<title>{p['title']}</title>\n"
        f"<url>{p['url']}</url>\n<content>\n{p['content'][:MAX_CHARS_PER_POST]}\n</content>\n</article>"
        for p in posts
    )
    return (
        f"다음은 {period} 기간의 valley.town 시황뉴스 게시물 {len(posts)}건입니다. "
        f"기간 전체를 종합한 시황 브리핑 문서를 작성해 주세요.\n\n{articles}"
    )


def summarize_deepseek(posts: list[dict], period: str) -> str:
    from openai import OpenAI

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError(".env에 DEEPSEEK_API_KEY를 설정하세요.")
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    log(f"DeepSeek API로 요약 중... (게시물 {len(posts)}건)")
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            max_tokens=8000,
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_message(posts, period)},
            ],
        )
    except Exception as e:
        if "Insufficient Balance" in str(e):
            raise RuntimeError(
                "DeepSeek 계정 잔액이 부족합니다. https://platform.deepseek.com 에서 "
                "충전하거나, claude 프로바이더를 사용하세요."
            ) from e
        raise
    usage = response.usage
    log(f"요약 완료 (입력 {usage.prompt_tokens:,} / 출력 {usage.completion_tokens:,} 토큰)")
    return response.choices[0].message.content


def summarize_claude(posts: list[dict], period: str) -> str:
    import anthropic

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError(".env에 ANTHROPIC_API_KEY를 설정하세요.")
    client = anthropic.Anthropic()

    log(f"Claude API로 요약 중... (게시물 {len(posts)}건)")
    with client.messages.stream(
        model="claude-opus-4-8",
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=SUMMARY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_message(posts, period)}],
    ) as stream:
        response = stream.get_final_message()
    log(
        f"요약 완료 (입력 {response.usage.input_tokens:,} / "
        f"출력 {response.usage.output_tokens:,} 토큰)"
    )
    return "".join(b.text for b in response.content if b.type == "text")


SUMMARIZERS = {"deepseek": summarize_deepseek, "claude": summarize_claude}
MODEL_LABEL = {"deepseek": "DeepSeek (deepseek-chat)", "claude": "Claude (claude-opus-4-8)"}


# ---------------------------------------------------------------- 텔레그램 전송


def _md_to_telegram_html(text: str) -> str:
    """마크다운을 텔레그램이 지원하는 단순 HTML로 변환한다."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"<b>\1</b>", text)
    lines = []
    for ln in text.splitlines():
        if ln.startswith("#"):
            lines.append(f"<b>{ln.lstrip('# ').strip()}</b>")
        elif ln.strip() == "---":
            lines.append("———")
        else:
            lines.append(ln)
    return "\n".join(lines)


def _split_chunks(text: str, limit: int = 3800) -> list[str]:
    """줄 단위로 끊어서 limit 이하의 덩어리로 나눈다."""
    chunks, current = [], ""
    for ln in text.splitlines(keepends=True):
        if len(current) + len(ln) > limit and current:
            chunks.append(current)
            current = ""
        current += ln
    if current.strip():
        chunks.append(current)
    return chunks


def notify_telegram(summary: str, period: str) -> None:
    """요약을 텔레그램 봇으로 전송한다."""
    import json
    import urllib.request

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 환경변수를 설정하세요.")

    chunks = _split_chunks(_md_to_telegram_html(summary))
    log(f"텔레그램으로 전송 중... ({len(chunks)}개 메시지)")
    for i, chunk in enumerate(chunks):
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=30)
        except urllib.error.HTTPError as e:
            # HTML 파싱 오류 등이 나면 플레인 텍스트로 재시도
            payload.pop("parse_mode")
            payload["text"] = re.sub(r"</?[a-z][^>]*>", "", chunk)
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=30)
    log("텔레그램 전송 완료")


# ---------------------------------------------------------------- 파이프라인


def run_pipeline(
    days: int = 7,
    provider: str = "deepseek",
    max_posts: int = 30,
    headed: bool = False,
    telegram: bool = False,
    progress=log,
) -> Path:
    """수집부터 문서 생성까지 전체 실행. 생성된 파일 경로를 반환한다."""
    if provider not in SUMMARIZERS:
        raise RuntimeError(f"지원하지 않는 프로바이더: {provider}")
    email = os.getenv("VALLEY_EMAIL")
    password = os.getenv("VALLEY_PASSWORD")
    if not email or not password:
        raise RuntimeError(".env에 VALLEY_EMAIL, VALLEY_PASSWORD를 설정하세요.")

    progress(f"최근 {days}일치 뉴스 수집을 시작합니다 ({MODEL_LABEL[provider]})")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        context_kwargs = {}
        if AUTH_STATE.exists():
            context_kwargs["storage_state"] = str(AUTH_STATE)
        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        if not is_logged_in(page):
            login(page, email, password)
            context.storage_state(path=str(AUTH_STATE))

        posts, period = collect_posts(page, days, max_posts)
        browser.close()

    if not posts:
        raise RuntimeError("본문을 가져온 게시물이 없습니다.")

    try:
        summary = SUMMARIZERS[provider](posts, period)
    except RuntimeError as e:
        # 딥시크 잔액 부족 시 Claude 키가 있으면 자동 폴백
        if (
            provider == "deepseek"
            and "잔액" in str(e)
            and os.getenv("ANTHROPIC_API_KEY")
        ):
            progress(f"⚠ {e} → Claude로 대신 요약합니다.")
            provider = "claude"
            summary = SUMMARIZERS[provider](posts, period)
        else:
            raise

    OUTPUT_DIR.mkdir(exist_ok=True)
    end_date = period.split(" ~ ")[-1]
    out_path = OUTPUT_DIR / f"{end_date}_최근{days}일_시황요약.md"
    sources = "\n".join(f"- [{p['date']}] [{p['title']}]({p['url']})" for p in posts)
    out_path.write_text(
        f"{summary}\n\n---\n\n## 원문 출처\n{sources}\n\n"
        f"*생성: {dt.datetime.now():%Y-%m-%d %H:%M} · {MODEL_LABEL[provider]}*\n",
        encoding="utf-8",
    )
    progress(f"✅ 문서 저장 완료: {out_path}")

    if telegram:
        notify_telegram(summary, period)

    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="valley.town 시황뉴스 요약기")
    parser.add_argument("--days", type=int, default=7, help="최근 N일치 수집 (기본 7)")
    parser.add_argument(
        "--provider", choices=list(SUMMARIZERS), default="deepseek", help="요약 모델"
    )
    parser.add_argument("--max-posts", type=int, default=30, help="최대 게시물 수")
    parser.add_argument("--headed", action="store_true", help="브라우저 창 표시")
    parser.add_argument(
        "--telegram", action="store_true", help="완료 후 텔레그램으로 요약 전송"
    )
    args = parser.parse_args()

    run_pipeline(
        days=args.days,
        provider=args.provider,
        max_posts=args.max_posts,
        headed=args.headed,
        telegram=args.telegram,
    )


if __name__ == "__main__":
    main()
