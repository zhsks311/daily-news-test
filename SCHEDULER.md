# Scheduler 운영 메모

이 repo의 목적은 매일 개발·경제 브리핑 Markdown을 GitHub에 저장해서 Slack 전송 실패/누락이 있어도 Obsidian에서 볼 수 있게 하는 것이다.

## 핵심 운영 방향

- 정규 cron job: `daily-dev-economy-brief-korean`
- 실행 시간: 매일 한국시간 오전 9시
- 산출물 경로: `briefings/YYYY-MM-DD.md`
- GitHub repo: `zhsks311/daily-news-test`
- push 대상: `main`

## 왜 GitHub에 저장하는가

Slack에 긴 Markdown/미디어가 안정적으로 올라가지 않을 수 있다. 그래서 최종 브리핑 본문을 repo에 commit/push하고, 사용자는 Obsidian Git 연동 또는 수동 pull로 `briefings/` 아래 Markdown을 읽는다.

## cron job 요구사항

cron 실행 에이전트는 다음을 해야 한다.

1. web/browser로 최근 24~48시간 개발·경제 이슈를 확인한다.
2. 개발 섹션은 백엔드 개발자의 실력 향상에 도움 되는 글을 우선한다: 분산 시스템, 데이터베이스, API 설계, 성능 튜닝, 장애 분석, observability, 보안, 운영 자동화, 대규모 트래픽 사례.
3. 카테고리마다 같은 템플릿을 반복하지 말고, 성격에 맞는 전용 구조로 정리한다.
4. 한국어 아침 브리핑을 Markdown으로 작성한다.
5. `briefings/YYYY-MM-DD.md`에 저장한다.
6. `git add`, `git commit`, `git push origin main`으로 GitHub에 올린다.
7. Slack에는 제목 링크 목록과 GitHub 파일 링크를 보낸다.

## 카테고리별 정리 원칙

- `Top 3`: 오늘 꼭 봐야 하는 이유와 행동 힌트 중심.
- `백엔드/개발 역량`: 문제 상황, 설계 선택지, 트레이드오프, 운영 체크리스트, 적용 아이디어 중심.
- `AI/인프라`: 바뀐 기능/정책, 실무 영향, 도입 전 확인할 리스크 중심.
- `경제/시장`: 숫자, 기준일, 시장 해석, 기술/반도체/한국 시장 연결 중심.
- `더 볼 것`: 짧은 후보 큐레이션. 왜 저장할 만한지만 1~2문장.
- `오늘의 질문`: 백엔드 설계/운영 의사결정으로 이어지는 질문을 우선.

## 권한

GitHub push는 repo 전용 deploy key로 한다. 개인 SSH key나 PAT를 쓰지 않는다.

## 로컬 collector

`src/briefing_collector`와 `scripts/cron_collect.py`는 수동 수집/검증용으로 유지한다. 현재 정규 cron은 host script 경로 문제를 피하기 위해 pre-run script에 의존하지 않는다.

검증:

```bash
cd /workspace/daily-briefing
.venv/bin/python -m pytest -q -o 'addopts='
git status --short --branch
git ls-remote origin refs/heads/main
```
