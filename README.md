# KANT AGENT

부트캠프 교육생이 출결 규정, 교육 일정, 프로젝트 공지를 검색하고 원문 근거와 함께 답변을 확인하는 Knowledge Agent입니다.

## 실행 환경

- Python 버전: [`.python-version`](.python-version)
- 의존성 설치 명령: <작성>
- 환경변수: [`.env.example`](.env.example) 참고
- 임베딩·생성·재정렬 모델 및 버전: <작성>

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

1. [문서 목록](data/sources.md)을 보고 입력 원문을 준비합니다. <재수집 방법 작성>
2. 전처리 및 색인 재생성
   - PGVector 실행(교안 RAG 2장 5강 이미지, 수업 실습용 컨테이너와 구분한 프로젝트 전용):
     `docker run -d --name kant-agent-pgvector -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=postgres -v kant_agent_pgdata:/var/lib/postgresql/data -p 5432:5432 pgvector/pgvector:pg17`
     - 수업용 컨테이너와 포트(5432)가 같아서 동시에 켜지 않습니다. 이후에는 `docker start kant-agent-pgvector`로 실행합니다.
   - `.env`에 `OPENAI_API_KEY`, `DATABASE_URL` 설정([`.env.example`](.env.example) 참고)
   - 색인 생성: `uv run python -m kant_agent.document_indexing.build_index`
     - 원문 → `data/processed/chunks.json` → PGVector 컬렉션 `kant_docs` 증분 적재(임베딩 `text-embedding-3-small`)
     - 다시 실행하면 바뀌지 않은 청크는 건너뜁니다(`num_skipped`).
     - `--chunks-only`: DB 없이 `chunks.json`만 생성
     - `--sample`: `data/sample/` → `data/processed/sample_chunks.json`, 컬렉션 `kant_docs_sample`
   - 검색 연결: `setup_search("data/processed/chunks.json", "kant_docs", "v1")`
3. 인터페이스 실행: <명령 작성>
4. 정상 답변·근거 없음 확인: <대표 질문과 예상 동작 작성>
5. 평가 실행: <명령, 구성 및 결과 저장 위치 작성>

설계와 범위는 [문제 정의](docs/problem.md), 평가 파일 형식은 [평가셋 안내](eval/README.md), 결과 해석은 [비교 보고서](report.md)에 기록합니다.

## 검색·재정렬 모듈

`kant_agent.search`의 `search(question, mode)`로 A(Vector),
B(BM25+Vector RRF), C(B+Cross-Encoder)를 선택합니다.
설정·실행 명령·팀 연결 계약·검증 범위는 [검색 안내](docs/search.md)를 참고하세요.
