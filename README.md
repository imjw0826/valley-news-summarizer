# Valley News Summarizer

valley.town의 [월가아재 시황칼럼 - 오늘의 핵심뉴스](https://www.valley.town/premium/wsaj-column/daily-news)에
올라온 **최근 N일치 게시물**을 자동으로 수집하고, DeepSeek 또는 Claude API로 요약해
기간 시황 브리핑 문서(마크다운)를 만듭니다. 핸드폰에서 쓸 수 있는 웹 UI도 포함되어 있습니다.

## 설치 (최초 1회)

```bash
cd ~/Documents/valley-news-summarizer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
# .env 파일을 열어 valley.town 계정과 API 키(DeepSeek 또는 Anthropic)를 입력
```

## 사용법 1 — 명령줄

```bash
source .venv/bin/activate
python valley_news.py                      # 최근 7일치, DeepSeek으로 요약
python valley_news.py --days 3            # 최근 3일치
python valley_news.py --provider claude   # Claude API 사용
python valley_news.py --headed            # 브라우저 창을 띄워서 디버깅
```

결과는 `output/` 폴더에 마크다운으로 저장됩니다.

## 사용법 2 — 웹 (핸드폰)

맥에서 서버를 켜두고:

```bash
source .venv/bin/activate
python app.py
```

실행하면 `📱 핸드폰에서 접속: http://<맥의 IP>:8765` 주소가 출력됩니다.
**같은 와이파이에 연결된** 핸드폰 브라우저에서 그 주소로 접속하면:

- 기간(1/3/7/14일)과 모델(deepseek/claude)을 골라 버튼 한 번으로 요약 생성
- 생성된 문서를 핸드폰에서 바로 읽기

> 맥이 켜져 있고 같은 네트워크에 있어야 합니다. 외부에서도 접속하고 싶으면
> Tailscale(무료) 설치를 추천 — 설치 후 같은 주소 형식으로 어디서든 접속됩니다.

## 모델 / 비용

| 프로바이더 | 모델 | 특징 |
|---|---|---|
| `deepseek` (기본) | deepseek-chat | 저렴함. https://platform.deepseek.com 에서 잔액 충전 필요 |
| `claude` | claude-opus-4-8 | 품질 우수. 7일치 요약 1회 ≈ 입력 3.7만 + 출력 5천 토큰 |

## 동작 방식

1. Playwright(헤드리스 Chromium)로 valley.town에 로그인
   - 세션은 `auth_state.json`에 저장되어 다음 실행부터 로그인 생략
2. 시황뉴스 피드를 스크롤하며 최근 N일치 게시물 링크 수집 → 각 게시물 본문 추출
3. LLM으로 기간 전체를 종합한 시황 브리핑 생성 (테마별 정리 + 시장 흐름 + 투자 시사점)
4. 마크다운 문서 저장 (원문 출처 링크 포함)

## 매일 자동 실행 (선택)

macOS에서 cron으로 매일 아침 8시에 실행하려면 `crontab -e` 후:

```
0 8 * * * cd $HOME/Documents/valley-news-summarizer && .venv/bin/python valley_news.py --days 1 >> output/run.log 2>&1
```

## 주의

- `.env`와 `auth_state.json`에는 민감한 정보가 담기므로 절대 공유/커밋하지 마세요 (`.gitignore`에 포함됨).
- 사이트 구조가 바뀌면 셀렉터(`collect_posts`)를 수정해야 할 수 있습니다.
- 수집한 콘텐츠는 본인 구독 계정의 개인적 용도로만 사용하세요.
