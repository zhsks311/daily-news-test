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
3. 한국어 아침 브리핑을 Markdown으로 작성한다.
4. `briefings/YYYY-MM-DD.md`에 저장한다.
5. `git add`, `git commit`, `git push origin main`으로 GitHub에 올린다.
6. Slack에는 제목 링크 목록과 GitHub 파일 링크를 보낸다.

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
