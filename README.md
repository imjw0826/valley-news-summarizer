# Valley News Summarizer

## 1. 프로젝트 소개

valley.town의 [월가아재 시황칼럼 - 오늘의 핵심뉴스](https://www.valley.town/premium/wsaj-column/daily-news)에 올라온 최근 며칠 치 게시물을 자동으로 모아 AI로 요약하는 도구입니다. 매일 글을 읽지 못해도 한 주의 시황을 브리핑 문서 한 편으로 받아 보는 것이 목적입니다.

## 2. 기술 스택

- **언어:** Python 3.12
- **수집:** Playwright (헤드리스 Chromium)
- **요약:** DeepSeek 또는 Anthropic Claude API
- **전송·열람:** 텔레그램 봇, Flask 웹 화면
- **자동화:** GitHub Actions

## 3. 이용 방법

valley.town 유료 구독 계정과 DeepSeek 또는 Anthropic API 키가 필요합니다.

**GitHub Actions로 실행 (컴퓨터 없이)**

1. 저장소를 포크하고 Settings → Secrets에 `VALLEY_EMAIL`, `VALLEY_PASSWORD`, `DEEPSEEK_API_KEY`(또는 `ANTHROPIC_API_KEY`), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`를 등록합니다.
2. **Actions → 주간 시황뉴스 요약 → Run workflow**에서 일수와 모델을 골라 실행합니다.
3. 몇 분 뒤 텔레그램으로 요약이 도착합니다.

현재 자동 예약 실행은 꺼져 있어 수동으로 실행해야 합니다.

**내 컴퓨터에서 실행**

```bash
git clone https://github.com/imjw0826/valley-news-summarizer.git
cd valley-news-summarizer
pip install -r requirements.txt
playwright install chromium
cp .env.example .env            # 로그인 정보와 API 키 입력

python valley_news.py --days 7 --provider deepseek   # 요약 문서 생성
python valley_news.py --days 7 --telegram            # 텔레그램으로도 전송
python app.py                                        # 같은 와이파이의 휴대폰에서 http://<컴퓨터 IP>:8765 접속
```

결과는 테마별 정리, 시장 흐름, 투자 시사점과 원문 링크가 담긴 마크다운 문서로 저장됩니다.

## 4. 최근 업데이트

2026-09-05
