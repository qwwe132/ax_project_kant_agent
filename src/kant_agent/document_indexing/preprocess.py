"""
Notion에서 내보낸 Markdown 사본을 청킹 전에 정리한다.
"""

import re

# ------------------------------------------------------------------
# 정규식 패턴 모음
# re.compile()로 패턴을 미리 만들어 두면 여러 문서에 반복해서
# 쓸 때 매번 새로 해석하지 않아도 된다. (정규식 특강 3절)
# 이름 앞의 밑줄(_)은 "이 파일 안에서만 쓰는 값"이라는 표시다.
# ------------------------------------------------------------------

# Notion 사본에서 섹션 제목으로 쓰이는 HTML 블록
# 예) <h3 color="brown_bg">
#      본인 및 자녀의 질병/입원
#     </h3>
# - ([23])  : 제목 단계(2 또는 3)를 1번 그룹으로 잡는다.
# - [^>]*   : color="..." 같은 속성은 무엇이 와도 넘어간다.
# - (((?!</?h[23]).)*?) : 제목 글자를 2번 그룹으로 잡는다.
#     (?!</?h[23]) 는 부정형 전방 탐색이다. (정규식 특강 8절)
#     "다음 글자가 <h2>·<h3>·</h2>·</h3> 의 시작이 아닐 때만"
#     한 글자씩 앞으로 간다. 닫는 태그가 빠진 제목이 있어도
#     다음 제목 태그를 넘어가 그 제목까지 먹지 않게 막는다.
# - </h\1>  : 1번 그룹과 같은 숫자의 닫는 태그(</h3>)를 찾는다.
# - DOTALL  : 제목이 여러 줄에 걸쳐 있어서 .이 줄바꿈도 포함하게 한다.
_HEADING_TAG = re.compile(
    r"<h([23])[^>]*>\s*(((?!</?h[23]).)*?)\s*</h\1>", re.DOTALL
)

# 접었다 펼 수 있는 "토글 제목" 블록
# 예) <toggle heading="h2">
#     1️⃣ 프로젝트 개요
# 여는 태그 다음 줄(2번 그룹)을 제목으로 본다.
# - [^>]*   : heading 앞뒤에 color="..." 같은 다른 속성이 있어도 넘어간다.
# - .h([23]). : 따옴표 자리에 . 을 써서 "h2" 와 'h2' 를 모두 잡는다.
_TOGGLE_HEADING = re.compile(
    r"<toggle[^>]*heading=.h([23]).[^>]*>\s*\n\s*([^\n]+)"
)

# 표 한 행(<tr>...</tr>)과 그 안의 칸
# 칸은 일반 칸 <td>와 머리글 칸 <th>를 모두 잡는다. t[dh] = td 또는 th
# 표가 여러 줄에 걸쳐 저장되어 있어 DOTALL이 필요하다.
_TABLE_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL)
_TABLE_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.DOTALL)

# 줄바꿈 태그. <br>, <br/>, <br /> 모두 잡는다.
_LINE_BREAK = re.compile(r"<br\s*/?>")

# 첨부 파일 링크만 있는 줄.
# 예) ![원본 첨부 이미지](./assets/image-03.png)   ← 이미지
#     [원본 첨부](./assets/notion-20261123-39.mp4) ← 영상·xlsx·html
# - !?      : 이미지 표시 "!"가 있어도(0번) 없어도(1번) 된다.
# - \./assets/ : 원문 사본의 첨부 폴더를 가리키는 링크만 지운다.
#             본문 속 일반 웹 링크는 남긴다.
# MULTILINE을 켜야 ^(줄 시작)과 $(줄 끝)가 문서 전체가 아니라
# 각 줄마다 적용된다. (정규식 특강 4절)
_ATTACHMENT_LINE = re.compile(
    r"^\s*!?\[[^\]]*\]\(\./assets/[^)]*\)\s*$", re.MULTILINE
)

# 남은 HTML 태그. <b>, </span>, <callout icon="💡"> 등
# 진짜 태그만 지우도록 조건을 좁힌다.
# - </?            : 여는 태그(<b>)와 닫는 태그(</b>) 둘 다
# - [A-Za-z]       : "<" 바로 뒤가 영문자여야 태그로 본다.
#                    "<09:10", "<유의 사항>" 같은 본문은 건드리지 않는다.
# - [A-Za-z0-9-]*  : 태그 이름의 나머지 (h3, table-of-contents 등)
# - [^<>\n]*       : 속성 부분. 줄바꿈(\n)을 넘지 않아서
#                    태그가 아닌 "<"가 다음 줄의 ">"까지 먹지 않는다.
_HTML_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9-]*[^<>\n]*>")

# Markdown 이스케이프. 예) "1\. 개강 전" → "1. 개강 전"
# 역슬래시 바로 뒤의 특수문자 하나를 1번 그룹으로 잡는다.
# "\<카페>" 같은 꺾쇠 표기도 "<카페>"로 되돌리려고 "<"를 포함한다.
_MARKDOWN_ESCAPE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!~|<>])")

# 줄 맨 앞에서 시작하는 짧은 굵은 글씨 한 줄 = 소제목
# 예) <b>훈련장려금</b>, <b>Pull Request (PR)</b>
# - ^<b>        : 들여쓰기 없이 줄 맨 앞에서 시작 (콜아웃 안 "🚨 참고사항"
#                 처럼 들여쓴 강조 문구는 제외)
# - ([^<\n]{1,30}) : 30자 이하 글자만. 긴 강조 문장은 제목이 아니다.
_BOLD_HEADING = re.compile(r"^<b>([^<\n]{1,30})</b>[ \t]*$", re.MULTILINE)

# 구분선만 있는 줄. 예) "---"
_HORIZONTAL_RULE = re.compile(r"^-{3,}[ \t]*$", re.MULTILINE)

# 세 줄 이상 연속된 줄바꿈(빈 줄 두 개 이상)
_EXTRA_BLANK_LINES = re.compile(r"\n{3,}")


def _heading_repl(match: re.Match[str]) -> str:
    """제목 태그 매치를 '###' 제목 형식의 Markdown 제목으로 바꾼다."""
    # sub()에 함수를 넘기면, 매치될 때마다 이 함수가 불리고
    # 함수가 돌려준 문자열로 그 자리를 바꾼다. (정규식 특강 9절)
    # match.group(1) = "3", match.group(2) = "본인 및 자녀의 질병/입원"
    level = int(match.group(1))
    # 제목 안에 <b> 같은 태그가 섞여 있을 수 있어 지운다.
    title = _HTML_TAG.sub("", match.group(2)).strip()
    # "#"을 level 개수만큼 붙인다. 3 → "### 본인 및 자녀의 질병/입원"
    # 앞뒤 줄바꿈은 제목이 다른 글과 붙지 않고 한 줄을 차지하게 한다.
    # chunking.py가 "## "·"### "로 시작하는 줄을 섹션 경계로 쓰기 때문이다.
    return "\n" + "#" * level + " " + title + "\n"


def _table_row_repl(match: re.Match[str]) -> str:
    """표 한 행 매치를 '칸1 | 칸2 | 칸3' 한 줄로 바꾼다."""
    # 표의 한 행은 "사유 - 인정 일수 - 필요 서류"처럼 하나의 정보다.
    # 칸이 여러 줄로 흩어져 있으면 청킹할 때 행 중간이 잘릴 수 있다.
    # 한 줄로 모아 두면 한 행의 내용이 같은 청크에 남는다.
    cells = []
    # findall()은 행 안의 모든 <td> 칸 내용을 리스트로 돌려준다.
    for cell in _TABLE_CELL.findall(match.group(1)):
        # 칸 안의 줄바꿈은 " / "로 이어서 한 행이 한 줄로 남게 한다.
        cell = _LINE_BREAK.sub(" / ", cell)
        cell = _HTML_TAG.sub("", cell)
        # split()은 공백·줄바꿈을 기준으로 나누고,
        # " ".join()으로 다시 이으면 여러 공백이 한 칸으로 줄어든다.
        cells.append(" ".join(cell.split()))
    # 칸 태그를 하나도 못 찾았으면 행 내용이 통째로 사라지지 않도록
    # 태그만 지운 글자를 그대로 한 줄로 남긴다.
    if not cells:
        row_text = _HTML_TAG.sub("", match.group(1))
        return " ".join(row_text.split()) + "\n"
    # 예) "질병/입원(본인, 자녀) | 전체 소정훈련일수의 10 퍼센트 | ..."
    # 마지막 칸들이 비어 있으면 "투표확인증 | " 처럼 끝에 "|"가 남는다.
    # rstrip(" |")는 오른쪽 끝의 공백과 "|"만 지운다.
    # 가운데 빈 칸은 그대로 두어 칸 순서(몇 번째 칸인지)는 유지한다.
    return " | ".join(cells).rstrip(" |") + "\n"


def clean_notion_markdown(text: str) -> str:
    """HTML 태그·이스케이프·이미지 줄을 정리한 Markdown을 반환한다."""
    # 순서 중요, 제목·표처럼 "모양"을 살려야 하는 태그를 먼저 바꾸고,
    # 그다음에 나머지 태그를 한꺼번에 지운다.
    # 순서를 바꾸면 <h3>가 먼저 지워져 섹션을 나눌 수 없게 된다.

    # 1) HTML 제목 → Markdown 제목(##, ###)
    text = _HEADING_TAG.sub(_heading_repl, text)
    text = _TOGGLE_HEADING.sub(_heading_repl, text)
    # 2) 표 한 행 → "칸1 | 칸2 | 칸3" 한 줄
    text = _TABLE_ROW.sub(_table_row_repl, text)
    # 2-1) 줄 맨 앞의 짧은 굵은 글씨 → "### 소제목"
    text = _BOLD_HEADING.sub(r"\n### \1\n", text)
    # 2-2) 구분선(---)은 검색에 의미가 없어 지운다.
    text = _HORIZONTAL_RULE.sub("", text)
    # 3) 남은 <br /> → 실제 줄바꿈
    text = _LINE_BREAK.sub("\n", text)
    # 4) 이미지·첨부 파일 링크 줄은 검색에 도움이 안 되어 지운다.
    text = _ATTACHMENT_LINE.sub("", text)
    # 5) 나머지 태그(<b>, <span>, <callout> 등)는 글자만 남기고 지운다.
    text = _HTML_TAG.sub("", text)
    # 6) "\." → "." 처럼 역슬래시를 떼고 1번 그룹 글자만 남긴다.
    text = _MARKDOWN_ESCAPE.sub(r"\1", text)
    # 7) 줄 끝 공백을 지우고, 빈 줄이 여러 개면 하나로 줄인다.
    lines = [line.rstrip() for line in text.splitlines()]
    return _EXTRA_BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()
