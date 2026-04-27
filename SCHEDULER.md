# Scheduler 운영 메모

현재 Hermes cron job `daily-dev-economy-brief-korean`은 pre-run script에 의존하지 않도록 설정한다.

이유:
- Slack/Hermes 스케줄러는 host 기준 `~/.hermes/scripts/`에서 script를 찾는다.
- Docker 작업공간의 `/workspace/daily-briefing/scripts/cron_collect.py`와 host 경로가 항상 같지 않다.
- script 경로가 어긋나면 `Script not found`가 발생한다.

운영 방향:
- cron prompt가 web/browser 도구로 직접 최근 24~48시간 개발·경제 뉴스를 확인한다.
- 출력은 한국어 아침 브리핑 형식으로 유지한다.
- 외부 사실은 URL 출처를 붙인다.

현재 권장 출력 구조:
1. 오늘의 Top 3
2. 개발/AI 요약
3. 경제/시장 요약
4. 오늘의 질문 3개
5. 출처 모음

로컬 collector는 수동 검증/향후 script-backed cron 복구용으로 유지한다.

```bash
cd /workspace/daily-briefing
.venv/bin/python -m pytest -q -o 'addopts='
./bin/collect-candidates --no-full-text --days 1 --per-category 3 \
  --output output/candidates.scheduler-smoke.json \
  --event-log logs/scheduler-smoke-events.jsonl
```
