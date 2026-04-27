# Daily Briefing Collector

매일 개발·경제 브리핑에 넣을 후보 글을 RSS 중심으로 수집하는 스크립트입니다.

## 구조

- `config/sources.toml`: 고정 RSS 소스 목록
- `src/briefing_collector/collector.py`: 수집, 날짜 필터, 중복 제거, 점수화, JSON/JSONL 이벤트 로그 출력
- `bin/collect-candidates`: venv 기반 실행 래퍼
- `output/candidates.json`: 후보 글 실행 결과
- `logs/collector-events.jsonl`: 누적 수집·정리 이벤트 로그
- `/root/.hermes/scripts/daily_briefing_collect.py`: Hermes cron pre-run 스크립트

## 설치

```bash
cd /workspace/daily-briefing
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 실행

```bash
./bin/collect-candidates \
  --days 1 \
  --per-category 12 \
  --output output/candidates.json \
  --event-log logs/collector-events.jsonl
```

빠른 메타데이터 수집만 할 때:

```bash
./bin/collect-candidates --no-full-text --days 1 --per-category 12
```

특정 실행을 로그에서 묶어 보려면:

```bash
./bin/collect-candidates --run-id manual-$(date -u +%Y%m%dT%H%M%SZ)
```

## 이벤트 로그

`logs/collector-events.jsonl`은 append-only JSONL입니다. 각 줄은 하나의 이벤트입니다.

주요 이벤트:

- `collection_start`, `collection_finish`: 실행 시작/종료, 설정값, 최종 후보 수
- `feed_fetch_start`, `feed_fetch_success`, `feed_fetch_error`: RSS 소스별 접근 성공/실패, 파싱 수, 지연 시간
- `feed_parse_summary`: 전체 RSS 파싱 후보 수
- `date_filter_summary`: 날짜 필터 전/후 후보 수
- `dedupe_summary`: 중복 제거 전/후 후보 수
- `article_fetch_start`, `article_fetch_success`, `article_fetch_error`: 원문 HTML fetch 성공/실패, 텍스트 길이, 지연 시간
- `article_fetch_summary`: 원문 fetch 총계
- `scoring_summary`: 점수화된 후보 수와 상위 후보 점수
- `selection_summary`: 카테고리별 최종 후보 수

로그 분석 예시:

```bash
# 실패한 피드/원문 fetch 보기
python3 - <<'PY'
import json
from pathlib import Path
for line in Path('logs/collector-events.jsonl').read_text().splitlines():
    e = json.loads(line)
    if e['event'].endswith('_error'):
        print(e['ts'], e['event'], e.get('source'), e.get('url'), e.get('error'))
PY
```

## 출력 정책

스크립트는 후보 수집과 수집 품질 로그까지만 담당합니다.
LLM은 `output/candidates.json`과 cron 주입 컨텍스트를 입력으로 받아 최종 선별, 원문 확인, 한국어 요약을 담당합니다.
