# KANT AGENT

부트캠프 교육생이 출결 규정, 교육 일정, 프로젝트 공지를 검색하고 원문 근거와 함께 답변을 확인하는 Knowledge Agent입니다.

## 실행 환경

- Python 버전: [`.python-version`](.python-version)
- 의존성 설치 명령: `uv sync --locked`
- 환경변수: [`.env.example`](.env.example) 참고
- 임베딩·생성·재정렬 모델 및 버전:
  - 생성: `gpt-6-luna` (`reasoning_effort="low"`, 출력 한도 `MAX_TOKENS=1000`), 프롬프트 `v5`(최종 평가는 `v4`, v5는 챗봇 이름만 "어둠의 마왕 다크타니"로 변경) — 값은 [`generator.py`](src/kant_agent/answer_generation/generator.py)의 `MODEL_NAME`, `PROMPT_VERSION`, `MAX_TOKENS`
  - 임베딩: `text-embedding-3-small` (OpenAI), 컬렉션 `kant_docs`, 색인 `v1` — 값은 [`build_index.py`](src/kant_agent/document_indexing/build_index.py)와 [`service.py`](src/kant_agent/search/service.py)의 `EMBEDDING_MODEL`
  - 재정렬: `Dongjin-kr/ko-reranker` (Cross-Encoder, 구성 C), 후보 `CANDIDATE_K=20`개 중 상위 `TOP_K=5`개 출력 — 값은 [`service.py`](src/kant_agent/search/service.py)의 `RERANKER_MODEL`, `CANDIDATE_K`, `TOP_K`

## 팀 공용 샘플 데이터

최신 작업 브랜치를 받은 팀원은 아래 가상 자료로 같은 입력을 재현할 수 있습니다.

| 파일 | 용도 |
| --- | --- |
| [출결 규정](data/sample/attendance.md), [공가 안내](data/sample/excused-absence.md), [시간표](data/sample/schedule.xlsx) | 문서·색인 담당의 로더 입력. 문서 ID는 각각 `SAMPLE-001`, `SAMPLE-002`, `SAMPLE-003`입니다. |
| [샘플 청크](data/fixtures/sample-chunks.json) | 로더나 DB 연결을 기다리는 동안 검색·답변 코드를 만들 때 사용할 청크 3개입니다. |
| [확인 질문 4개](eval/sample.json) | 실행 검증용입니다. 실행 코드에는 `question`을 전달하고, 기대 답변과 허용 근거는 결과 확인에 사용합니다. |

### 역할별 사용 방법

1. **문서·색인** 담당은 `data/sample/`의 원문 3개를 읽고 샘플 전용 DB 또는 색인에 적재합니다. 날짜·시간·일정이 한 청크에 남는지 확인하고, `chunk_id`, `document_id`, `text`, `source_path`, `source_location`을 검색 담당에게 전달합니다.
2. **검색·재정렬** 담당은 실제 색인 연결 전에는 샘플 청크 배열을 입력으로 사용합니다. 확인 질문 1~3에서 각각 해당 문서가 후보에 포함되는지 확인하고, 순서가 있는 검색 결과를 답변 담당에게 전달합니다.
3. **답변·인터페이스** 담당은 샘플 청크를 검색 결과로 전달해 답변과 출처를 먼저 연결합니다. 개인별 출석률 질문은 정보 부족으로 처리되며, 호출 오류는 별도 상태로 표시되는지 확인합니다.
4. **최적화·평가** 담당은 `eval/sample.json`을 순회해 질문 ID, 검색 후보, 답변, 인용, 시간, 상태를 기록합니다. 근거는 문서 ID와 원문 위치로 대조합니다. 샘플 청크 ID는 임시 값이므로 실제 색인에서 생성한 ID는 실행 기록에서 확인합니다.

첫 통합은 **지각 질문 1개**로 원문 읽기 → 청킹·색인 → 검색 → 답변·출처 → 실행 기록까지 연결합니다. 그다음 공가, XLSX 시간표, 근거 없음까지 4문항을 돌려 확인합니다. 통합 실행 명령은 각 기능이 연결되면 아래 재현 순서에 추가합니다.

샘플 색인의 입력은 `data/sample/`로 지정하세요. `eval/`의 질문·정답표는 색인 대상에서 제외하고, 실제 실험은 운영 원문과 개발·최종 평가셋으로 수행합니다.

## 재현 순서

1. [문서 목록](data/sources.md)을 보고 입력 원문을 준비합니다. 2026-11-23에 수집한 원문 사본이 `data/raw/notion/`에 들어 있으므로 그대로 재현할 때는 이 단계를 건너뜁니다. 원문이 바뀌어 다시 받을 때는 아래 순서를 따릅니다.
   - Notion 문서(NOTION-001~018): 문서 목록의 출처 링크를 열어 Markdown으로 저장하고, 원문 위치 열의 파일(예: `data/raw/notion/attendance-fraud.md`)에 덮어씁니다. 첨부 이미지·파일은 `data/raw/notion/assets/`에 둡니다.
   - 파일 맨 위 머리말(`- 문서 ID: NOTION-015`, `- Notion 원문`, `- 수집일`, `- Notion 최종 수정 시각`)은 유지하고 수집일과 수정 시각만 고칩니다. 색인은 이 문서 ID가 문서 목록과 다르면 멈춥니다.
   - 시간표(NOTION-019): 구글 시트를 xlsx로 내려받아 `data/raw/notion/assets/KANT_AX_시간표.xlsx`에 덮어씁니다.
   - 문서 목록의 `버전 또는 수집일` 열을 고치고, 2번으로 색인을 다시 만든 뒤 평가·캐시의 `--index-version`을 올립니다.
2. 전처리 및 색인 재생성: 루트 `.env`에 [`.env.example`](.env.example)의 `OPENAI_API_KEY`, `DATABASE_URL`을 채운 뒤 레포 루트에서 실행합니다.
   ```
   uv run python -m kant_agent.document_indexing.build_index
   ```
   정상이면 마지막 로그에 `문서 18개, 청크 394개 -> data/processed/chunks.json`이 나옵니다. NOTION-011은 본문이 첨부 링크뿐이라 색인에서 제외됩니다([문서 목록](data/sources.md) 참고). DB 적재 없이 청크 파일만 다시 만들려면 `--chunks-only`를 붙입니다.
3. 인터페이스 실행: 2번의 색인과 `.env`(`OPENAI_API_KEY`, `DATABASE_URL`)가 준비된 상태에서 터미널 두 개를 엽니다.
   ```
   uv run uvicorn main:app --app-dir src --port 8000
   uv run streamlit run src/ui/app.py
   ```
   API는 시작할 때 재정렬 모델을 불러오느라 수십 초가 걸립니다. `Application startup complete` 로그가 나온 뒤 브라우저에서 `http://localhost:8501`을 엽니다. 화면은 `http://127.0.0.1:8000`의 API를 호출하므로 API 포트는 8000으로 둡니다. 배경 그림은 레포 루트의 `.streamlit/config.toml`(정적 파일 서빙)을 읽어야 나오므로 반드시 레포 루트에서 실행하고, 설정을 바꾼 뒤에는 Streamlit을 다시 시작합니다.
4. 정상 답변·근거 없음 확인: 화면에서 아래 질문을 입력합니다.

   | 질문 | 예상 동작 |
   | --- | --- |
   | 몇 시부터 지각이야? | 보라 말풍선, "09:10 이후 입실하면 지각" + `[1]`, "참고 자료 보기"에 `[KANT] 출석 및 공가 신청 가이드` Notion 링크 |
   | 11월 27일 시간표 알려줘 | 보라 말풍선, `09:00~13:00·14:00~18:00` 일정 + `KANT AX 시간표` 링크 |
   | 회사 주차 요금은 얼마야? | 남색 말풍선, 근거 없음 안내("흐음… 본좌의 서고에는 그런 기록이 없구나. 운영 담당자에게 직접 물어보거라."), 참고 자료 없음 |
   | 안녕 | 보라 말풍선, 짧은 인사(일반 대화), 참고 자료 없음 |
   | (API 서버를 끈 상태에서) 아무 질문 | 붉은 말풍선 `CONNECTION_ERROR` |

   답변 문장은 매번 조금씩 다를 수 있습니다. 시간, 상태, 근거 문서가 위와 같으면 정상입니다.
5. 평가 실행: 프로젝트 환경에서 `uv run`으로 실행합니다. `python`으로 직접 실행하면 `kant_agent` 모듈을 찾지 못합니다. 루트 `.env`에 `OPENAI_API_KEY`가 필요합니다.
   ```
   uv run python src/eval/run_eval.py <run_id> <stub|A|B|C> <eval_file> --kind <smoke|dev|final> --index-version <v1>
   uv run python src/eval/ragas_eval.py <run_id> <eval_file> --kind <kind>
   uv run python src/eval/failure_analyzer.py <run_id> --kind <kind>
   uv run python src/eval/compare.py <baseline_run_id> <improved_run_id> --kind <kind>
   uv run python src/eval/score.py <run_id> <eval_file> --kind <kind>
   ```
   결과는 `results/<kind>/`에 저장됩니다. `<run_id>.jsonl`(실행 원본), `_ragas.csv`(Ragas 4지표), `_diagnosis.csv`(실패 진단), `compare_*.csv`(회귀 비교), `_scoring.csv`(수동 채점표). 같은 run_id는 덮어쓰지 않으니 새로 실행할 때는 새 run_id를 씁니다.

   캐시 실험만 `--cache`를 붙입니다. A/B/C 비교와 최종 평가에서는 붙이지 않습니다. 문서를 다시 색인하면 `--index-version`을 올려야 이전 캐시를 쓰지 않습니다. 캐시 파일 `.cache/`는 커밋하지 않습니다.
   ```
   uv run python src/eval/run_eval.py cache-1-miss C eval/cache.json --kind dev --index-version v1 --cache
   ```

설계와 범위는 [문제 정의](docs/problem.md), 평가 파일 형식은 [평가셋 안내](eval/README.md), 결과 해석은 [비교 보고서](report.md)에 기록합니다.

## 검색·재정렬 모듈

`kant_agent.search`의 `search(question, mode)`로 A(Vector),
B(BM25+Vector RRF), C(B+Cross-Encoder)를 선택합니다.
