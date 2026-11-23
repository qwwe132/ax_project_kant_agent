# 🧑‍💻 개발 협업 툴&용어 정리.zip (1)

- 문서 ID: NOTION-003
- 분류: KANT 문화 가이드
- Notion 원문: https://app.notion.com/p/4216d0d25caa80f5bc8ae6957767d410
- 수집일: 2026-11-23
- Notion 최종 수정 시각: 2026-11-23T01:53:09.435Z

<p>
개발 경험이 없어도 수업과 프로젝트를 따라가기 위해 꼭 알아야 할 협업 용어, 질문법, AI 활용법을 정리했습니다. 
</p>

---

## 1. 개발 협업 101

✅ 개발 협업은 파일을 주고받는 일이 아니라, 여러 사람이 고친 내용을 안전하게 합치는 일입니다.

<table header-row="true">
<colgroup>
<col />
<col width="454" />
</colgroup>
<tr>
<td>
용어
</td>
<td>
설명
</td>
</tr>
<tr>
<td>
<b>Git</b>
</td>
<td>
코드 변경 이력을 관리하는 도구
</td>
</tr>
<tr>
<td>
<b>GitHub</b>
</td>
<td>
Git 저장소를 팀이 함께 쓰는 온라인 협업 플랫폼
</td>
</tr>
<tr>
<td>
<b>Repository (저장소)</b>
</td>
<td>
프로젝트 폴더의 원격 저장소
</td>
</tr>
<tr>
<td>
<b>Branch (브랜치)</b>
</td>
<td>
메인 작업물과 분리해서 안전하게 수정하는 작업선
</td>
</tr>
<tr>
<td>
<b>Commit (커밋)</b>
</td>
<td>
변경 사항을 저장하는 단위
</td>
</tr>
<tr>
<td>
<b>Pull Request (PR)</b>
</td>
<td>
내 변경 사항을 합치기 전에 리뷰받는 요청
</td>
</tr>
<tr>
<td>
<b>Code Review</b>
</td>
<td>
합치기 전 동료가 코드·설계를 검토하는 과정
</td>
</tr>
<tr>
<td>
<b>Issue (이슈)</b>
</td>
<td>
해야 할 일, 버그, 요청사항을 기록하는 단위
</td>
</tr>
<tr>
<td>
<b>Merge Conflict</b>
</td>
<td>
같은 파일을 서로 다르게 고쳐서 충돌한 상태
</td>
</tr>
</table>

---

## 2. 프로젝트 관리 용어 (Jira·칸반보드·애자일)

✅ 칸반보드는 "업무의 현재 위치를 볼 수 있는 곳"입니다. 누구 일이 많은지, 어디서 막혔는지, 다음에 무엇을 해야 하는지 한눈에 보기 위해 씁니다.

<table header-row="true">
<colgroup>
<col width="180.34375" />
<col width="505" />
</colgroup>
<tr>
<td>
용어
</td>
<td>
설명
</td>
</tr>
<tr>
<td>
<b>Jira</b>
</td>
<td>
이슈·업무·스프린트를 관리하는 프로젝트 관리 도구
</td>
</tr>
<tr>
<td>
<b>칸반보드 (Kanban Board)</b>
</td>
<td>
할 일 → 진행 중 → 리뷰 중 → 완료처럼 업무 흐름을 시각화한 보드
</td>
</tr>
<tr>
<td>
<b>Backlog</b>
</td>
<td>
아직 시작하지 않았지만 해야 할 일 목록
</td>
</tr>
<tr>
<td>
<b>Sprint</b>
</td>
<td>
정해진 기간 동안 끝낼 일을 묶는 반복 주기
</td>
</tr>
<tr>
<td>
<b>Epic</b>
</td>
<td>
여러 작업을 묶는 큰 목표
</td>
</tr>
<tr>
<td>
<b>User Story</b>
</td>
<td>
"사용자로서 무엇을 원한다" 형식의 요구사항
</td>
</tr>
<tr>
<td>
<b>Task</b>
</td>
<td>
실제 수행 단위
</td>
</tr>
<tr>
<td>
<b>Bug</b>
</td>
<td>
기대와 다르게 동작하는 문제
</td>
</tr>
<tr>
<td>
<b>WIP (Work In Progress)</b>
</td>
<td>
동시에 진행 중인 일을 제한하는 규칙
</td>
</tr>
<tr>
<td>
<b>Agile (애자일)</b>
</td>
<td>
계획을 한 번에 고정하지 않고, 짧은 주기로 만들고 확인하며 개선하는 방식
</td>
</tr>
</table>

---

## 3. 질문 잘하는 법 📝

더 빠르고, 정확한 답변을 받고 싶을 때, 다음과 같은 질문 방식을 활용해보세요.

<callout color="gray_bg">
<b><span color="red">\[상황\]</span></b>

<b><span color="red">무엇을 하려고 했나요?</span></b>

<b><span color="red">\[기대 결과\]</span></b>

<b><span color="red">원래는 어떻게 되어야 하나요?</span></b>

<b><span color="red">\[실제 결과\]</span></b>

<b><span color="red">어떤 에러/화면/로그가 나왔나요?</span></b>

<b><span color="red">\[시도한 것\]</span></b>

<b><span color="red">검색한 키워드, 실행한 명령어, 참고한 링크는 무엇인가요?</span></b>

<b><span color="red">\[환경\]</span></b>

<b><span color="red">OS, Python/Node 버전, 브라우저, 사용한 라이브러리 버전</span></b>
</callout>

📌 TIP

- "안 돼요"만 있는 질문은 다시 물어볼 수 있어요 상황을 구체적으로 설명하면 빠르고 정확한 도움을 받을 수 있습니다.
- 에러 메시지는 이미지보다 텍스트로 붙이는 것이 검색과 복사에 유리합니다.
- 질문은 무엇이 안 되는지 + 어디에서 안 되는지 쓰면 좋습니다.

---

## 4. AI 답변 검증법 🤖

- AI 답변은 좋은 출발점이 되는 초안으로 활용하면 좋습니다.
- 최신 라이브러리 버전, 설치 명령어, API 사용법은 공식 문서로 한 번 더 확인하면 정확합니다.
- 데이터 보안, 비용, 개인정보까지 함께 점검하면 완성도가 높아집니다.
- 출처·실행 결과·테스트 케이스를 같이 남기면 신뢰도가 올라갑니다.

---

## 5. 트랙별 핵심 용어 맛보기

<i>첫 주에는 이름만 알아두면 됩니다. 자세한 내용은 각 트랙 페이지에서 다룹니다.</i>

데이터사이언스

- SQL: 데이터베이스에서 원하는 데이터를 꺼내는 질의 언어
- EDA: 모델링 전에 데이터 구조·분포·이상치를 탐색하는 단계
- 머신러닝: 데이터에서 패턴을 학습해 예측·분류하는 방법

Physical AI

- ROS2: 로봇 소프트웨어를 모듈화해 통신시키는 프레임워크
- SLAM: 로봇이 지도를 만들면서 자기 위치를 추정하는 기술
- Isaac Sim: 로봇 시뮬레이션 환경

LLM

- Token / Embedding: 텍스트를 모델이 처리하는 단위 / 숫자 벡터로 바꾼 표현
- RAG: 외부 문서를 검색해 답변 근거로 쓰는 방식
- Fine-tuning: 기존 모델을 특정 데이터에 맞게 추가 학습하는 과정

AI 에이전트

- Tool Calling: LLM이 외부 도구·API를 호출하는 방식
- LangGraph: 상태 기반 에이전트 흐름을 설계하는 도구
- HITL (Human-in-the-loop): 중요한 결정에 사람의 승인·검토를 넣는 방식
