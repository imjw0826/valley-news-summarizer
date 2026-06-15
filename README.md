# Valley News Summarizer

valley.town의 [월가아재 시황칼럼 - 오늘의 핵심뉴스](https://www.valley.town/premium/wsaj-column/daily-news)에
올라온 **최근 N일치 게시물**을 자동으로 수집하고, DeepSeek 또는 Claude API로 요약해
기간 시황 브리핑 문서를 만듭니다.

## ☁️ 핸드폰 전용 사용법 (컴퓨터 없이) — GitHub Actions + 텔레그램

**매주 토요일 아침 8시(KST)** GitHub Actions가 자동으로 일주일치 뉴스를 요약해서
**텔레그램 메시지로 보내줍니다.** 컴퓨터가 꺼져 있어도 동작합니다.

### 원할 때 즉시 실행 (수동 트리거)

GitHub 모바일 앱(또는 브라우저) → `valley-news-summarizer` 저장소 →
**Actions → 주간 시황뉴스 요약 → Run workflow** → 일수/모델 선택 후 실행.
몇 분 뒤 텔레그램으로 요약이 도착합니다.

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

