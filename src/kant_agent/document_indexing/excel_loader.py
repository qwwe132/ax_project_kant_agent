"""
엑셀(xlsx) 원문을 검색 담당에게 넘길 청크로 나눈다.
청크 필드: chunk_id, document_id, text, source_path, source_location

다루는 xlsx 모양은 두 가지다.
1) 일반 표: 첫 행이 머리글(날짜, 시간, 일정 ...)이고 아래로 데이터 행
    예) data/sample/schedule.xlsx → 한 행 = 청크 하나
2) 주차별 격자 시간표: 같은 모양의 "주차 블록"이 아래로 반복됨
    예) KANT_AX_시간표.xlsx → 하루(날짜 열 하나) = 청크 하나
"""

import json
import sys
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from kant_agent.shared.core.logger import get_logger

# __name__ = "kant_agent.document_indexing.excel_loader"
logger = get_logger(__name__)

# datetime.weekday()가 돌려주는 0~6을 요일 글자로 바꿀 때 쓴다.
# 0 = 월요일, 6 = 일요일
WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]

# ------------------------------------------------------------------
# 주차별 격자 시간표의 생김새 (1주차 블록 예시, 엑셀 행 번호 기준)
#
#   2행  | B: 1주차
#   3행  | B: 시작시간 | C: ~ | D: 종료시간 | E~I: 2026-08-03 ~ 08-07
#   4행  | E~I: 교과명
#   5행  | B: 09:00 | D: 10:00 | E~I: 그 시간의 교과명 (월~금)
#   ...    (09:00~18:00, 1시간씩 9줄)
#   13행 | B: 17:00 | D: 18:00 | ...
#   14~18행 | B: [원격]강의명, [프로젝트], [프로젝트]소주제,
#             과제/테스트/기타, 비고 | E~I: 날짜별 추가 정보
#
# 이 17줄 블록이 1주차~41주차까지 아래로 반복된다.
# ------------------------------------------------------------------

# 주간 시간표 블록에서 각 값이 들어 있는 열 번호(0부터 센다)
# 예) B열 = 1, D열 = 3, E열 = 4, I열 = 8
_TIME_START_COL = 1
_TIME_END_COL = 3
_FIRST_DAY_COL = 4
_LAST_DAY_COL = 8
# 09:00~18:00을 1시간씩 나눈 9칸
_SLOT_COUNT = 9
# 시간 칸 아래의 추가 정보 줄 수: [원격]강의명, [프로젝트],
# [프로젝트]소주제, 과제/테스트/기타, 비고
_INFO_ROW_COUNT = 5

# 시간표 오른쪽(K~L열)에 따로 있는 "단위기간별 제적 기준표"
# 제목 칸의 글자와 열 번호(K열 = 10, L열 = 11)
_DISMISSAL_TITLE = "단위 기간 별 훈련일수에 따른 제적 기준"
_PERIOD_COL = 10
_RULE_COL = 11

# 표 형태 시간표에서 본문에 넣지 않을 열
# md 머리말의 "자료 구분"처럼 내용이 아니라 꼬리표 성격이라서 뺀다.
_EXCLUDED_COLUMNS = ["자료 구분"]


def _cell_name(row_index: int, col_index: int) -> str:
    """0부터 세는 행·열 번호를 엑셀 셀 이름(예: I275)으로 바꾼다."""
    # 열: ord("A") = 65에 열 번호를 더해 글자로 바꾼다. 8 → "I"
    #     A~Z 한 글자 열까지만 다룬다. 지금 원문은 L열까지만 쓴다.
    # 행: pandas 행 번호는 0부터, 엑셀 행 번호는 1부터라서 1을 더한다.
    #     274 → "275"
    return chr(ord("A") + col_index) + str(row_index + 1)


def _clean_text(value: object) -> str:
    """셀 안의 줄바꿈과 여러 공백을 공백 하나로 정리한다."""
    # split()은 공백·줄바꿈을 기준으로 나누고, " ".join()으로 다시 잇는다.
    # "추석 연휴\n대체공휴일" -> "추석 연휴 대체공휴일"
    return " ".join(str(value).split())


def _make_chunk(
    document_id: str,
    number: int,
    text: str,
    source_path: str,
    source_location: str,
) -> dict:
    """md 청크와 같은 5개 필드를 가진 청크 딕셔너리를 만든다."""
    # 검색·답변 담당이 md 청크와 똑같이 다룰 수 있도록 필드를 맞춘다.
    # {number:03d}는 숫자를 3자리로 채운다. 7 → "007"
    return {
        "chunk_id": f"{document_id}-{number:03d}",
        "document_id": document_id,
        "text": text,
        "source_path": source_path,
        "source_location": source_location,
    }


def _load_table(file_path: Path, document_id: str, sheet_name: str) -> list[dict]:
    """머리글이 있는 일반 표를 한 행씩 청크로 만든다."""
    # 첫 행을 머리글(열 이름)로 읽는다. 예) 날짜, 시간, 일정, 자료 구분
    # 그러면 df["일정"]처럼 열 이름으로 값을 꺼낼 수 있다.
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    columns = [c for c in df.columns if c not in _EXCLUDED_COLUMNS]
    # 사용하는 열 중 가장 오른쪽 열 번호, 위치를 A2:C2처럼 쓰는 데 쓴다.
    # get_loc("일정") → 2 (C열)
    last_col = max(df.columns.get_loc(c) for c in columns)

    chunks = []
    for row_index in range(len(df)):
        # iloc[번호]로 한 행을 꺼낸다. (Pandas 특강 3.1)
        row = df.iloc[row_index]
        parts = []
        for column in columns:
            value = row[column]
            # 빈칸(NaN)은 글에 넣지 않는다. (Pandas 특강 3.3.1 isna)
            if pd.isna(value):
                continue
            # 날짜 칸은 pandas가 Timestamp로 읽으므로 "2026-12-01"로 바꾼다.
            if isinstance(value, pd.Timestamp):
                value = value.strftime("%Y-%m-%d")
            # 칸 이름을 붙여서 "09:00~10:00"이 무엇인지 알 수 있게 한다.
            parts.append(f"{column}: {_clean_text(value)}")
        # 모든 칸이 빈 행은 청크로 만들지 않는다.
        if not parts:
            continue
        # 머리글이 1행이라 데이터 첫 행은 엑셀 2행이다(row_index + 1).
        # 결과 예) "시간표!A2:C2"
        location = (
            f"{sheet_name}!{_cell_name(row_index + 1, 0)}"
            f":{_cell_name(row_index + 1, last_col)}"
        )
        chunks.append(
            _make_chunk(
                document_id,
                len(chunks) + 1,
                # "날짜: 2026-12-01 | 시간: 09:00~10:00 | 일정: RAG 실습"
                " | ".join(parts),
                file_path.as_posix(),
                location,
            )
        )
    return chunks


def _day_text(
    df: pd.DataFrame, header_row: int, col: int, week: str
) -> tuple[str, int]:
    """주간 시간표의 하루(열 하나)를 한 단락 글로 만든다.

    header_row: "시작시간"·날짜가 있는 줄의 행 번호
    col: 그 날짜가 있는 열 번호(E~I열 = 4~8)
    반환값: (청크 글, 글에 쓰인 마지막 행 번호)
    """
    # 날짜 줄에서 이 열의 날짜를 꺼낸다. pandas가 datetime으로 읽는다.
    day = df.iat[header_row, col]
    # 날짜 줄 아래는 "교과명" 줄이고, 그 아래부터 시간 칸이 시작된다.
    first_slot = header_row + 2
    # 시간 칸 9줄만 잘라낸다. (Pandas 특강 3.1 iloc 슬라이싱)
    slot_rows = df.iloc[first_slot : first_slot + _SLOT_COUNT]

    # 병합 셀은 _fill_merged_cells()에서 이미 채워 두었다.
    # 여기서 남은 빈칸(NaN)은 원문에 정말 일정이 없는 칸이라 건너뛴다.
    # 예) 2027-05-12 수료식은 11:00~13:00만 적혀 있고 오후는 빈칸이다.
    subjects = slot_rows[col]

    # 같은 교과가 이어지는 시간은 하나로 합친다.
    # 예) 09:00~10:00 입학식, 10:00~11:00 입학식 -> 09:00~11:00 입학식
    # segments에는 [시작 시각, 끝 시각, 교과명]을 담는다.
    segments = []
    for slot_index in range(_SLOT_COUNT):
        if pd.isna(subjects.iloc[slot_index]):
            continue
        subject = _clean_text(subjects.iloc[slot_index])
        # 시작·종료 시각은 B열·D열에 time으로 들어 있다. 09:00:00 → "09:00"
        start = slot_rows.iat[slot_index, _TIME_START_COL].strftime("%H:%M")
        end = slot_rows.iat[slot_index, _TIME_END_COL].strftime("%H:%M")
        # 교과가 같고, 앞 구간이 끝난 시각에 바로 이어질 때만 합친다.
        # 중간에 빈칸이 있으면 시간이 끊기므로 새 구간으로 둔다.
        if segments and segments[-1][2] == subject and segments[-1][1] == start:
            # 바로 앞 구간과 교과가 같으면 끝 시각만 늘린다.
            segments[-1][1] = end
        else:
            # 교과가 바뀌면 새 구간을 시작한다.
            segments.append([start, end, subject])

    # 결과 예) "2026-11-27(금) 17주차 시간표: 09:00~13:00 프로젝트(3): ..."
    # 날짜·요일·주차를 앞에 붙여서 "다음 수업", "11월 27일" 같은
    # 질문에 이 청크가 검색되도록 한다.
    weekday = WEEKDAYS[day.weekday()]
    lines = [
        f"{day.strftime('%Y-%m-%d')}({weekday}) {week} 시간표: "
        + ", ".join(f"{s}~{e} {name}" for s, e, name in segments)
    ]

    # 시간 칸 아래 추가 정보(프로젝트 소주제, 비고 등)가 있으면 붙인다.
    # 예) "비고: 1 단위기간 종료(8/3 ~ 9/2) 단위기간 내 11일 이상 결석 시 제적"
    last_row = first_slot + _SLOT_COUNT - 1
    # 추가 정보가 없으면 마지막 시간 칸(17:00 줄)이 이 청크의 끝 행이다.
    end_row = last_row
    for info_row in range(last_row + 1, last_row + 1 + _INFO_ROW_COUNT):
        # 마지막 주차 블록은 파일 끝에서 잘릴 수 있어 범위를 확인한다.
        if info_row >= len(df):
            break
        value = df.iat[info_row, col]
        if pd.isna(value):
            continue
        # B열의 항목 이름(예: "비고")을 칸 이름처럼 앞에 붙인다.
        label = _clean_text(df.iat[info_row, _TIME_START_COL])
        lines.append(f"{label}: {_clean_text(value)}")
        # 실제로 글에 들어간 마지막 줄까지를 원문 위치로 쓴다.
        end_row = info_row
    return "\n".join(lines), end_row


def _dismissal_text(df: pd.DataFrame) -> tuple[str, int, int] | None:
    """단위기간별 제적 기준표를 찾아 한 단락 글로 만든다.

    반환값: (청크 글, 첫 행 번호, 마지막 행 번호). 표가 없으면 None
    """
    # K열에서 제목 칸에 있는 행 번호를 찾는다.
    # df[열] == 값 → True/False 목록(불리언 마스크, Pandas 특강 3.2)
    # df.index[마스크] → True인 행의 번호만 남는다.
    title_rows = df.index[df[_PERIOD_COL] == _DISMISSAL_TITLE].tolist()
    if not title_rows:
        return None

    lines = [_DISMISSAL_TITLE]
    first_row = None
    last_row = None
    # 제목 다음 줄부터 아래로 내려가며 표의 각 행을 읽는다.
    for row_index in range(title_rows[0] + 1, len(df)):
        period = df.iat[row_index, _PERIOD_COL]
        if pd.isna(period):
            # 제목 바로 아래 빈 줄은 건너뛰고, 표가 끝나면 멈춘다.
            if first_row is None:
                continue
            break
        rule = _clean_text(df.iat[row_index, _RULE_COL])
        # 예) "1 단위기간: 2026-08-03 ~ 2026-09-02 (22일) : 11일 이상 ..."
        lines.append(f"{_clean_text(period)}: {rule}")
        # 첫 데이터 행과 마지막 데이터 행을 기록해 위치(K4:L13)로 쓴다.
        if first_row is None:
            first_row = row_index
        last_row = row_index
    return "\n".join(lines), first_row, last_row


def _fill_merged_cells(df: pd.DataFrame, file_path: Path, sheet_name: str) -> None:
    """엑셀에서 실제로 병합된 범위만 첫 칸의 값으로 채운다.

    pandas는 병합 정보를 읽지 못해서, 병합 셀은 첫 칸에만 값이 있고
    나머지는 빈칸(NaN)으로 들어온다. 그렇다고 빈칸을 모두 위 값으로
    채우면(ffill) 원래 비어 있던 칸까지 채워져 원문에 없는 일정이
    생긴다. 그래서 openpyxl로 병합 범위 목록을 읽어 그 안만 채운다.
    """
    # merged_cells.ranges: "E515:E523" 같은 병합 범위 목록
    sheet = load_workbook(file_path)[sheet_name]
    for merged in sheet.merged_cells.ranges:
        # openpyxl 행·열 번호는 1부터, pandas는 0부터라서 1을 뺀다.
        first_row = merged.min_row - 1
        first_col = merged.min_col - 1
        # 교과명이 들어가는 요일 열(E~I)의 병합만 채운다.
        # B열 "시작시간"처럼 머리글 칸의 병합까지 채우면
        # 주차 블록의 날짜 줄을 찾는 기준이 흐트러진다.
        if not _FIRST_DAY_COL <= first_col <= _LAST_DAY_COL:
            continue
        if first_row >= len(df):
            continue
        value = df.iat[first_row, first_col]
        for row_index in range(first_row, merged.max_row):
            for col_index in range(first_col, merged.max_col):
                if row_index >= len(df) or col_index >= len(df.columns):
                    continue
                # 이미 값이 있는 칸(날짜 등)은 덮어쓰지 않고 빈칸만 채운다.
                if pd.isna(df.iat[row_index, col_index]):
                    df.iat[row_index, col_index] = value


def _load_weekly_timetable(
    file_path: Path, document_id: str, sheet_name: str
) -> list[dict]:
    """주차별 격자 시간표를 하루씩 청크로 만든다."""
    # 머리글 없이(header=None) 칸 위치 그대로 읽는다.
    # 같은 모양의 주차 블록이 아래로 반복되는 구조라서다.
    # 그래서 열 이름 대신 숫자(0, 1, 2 ...)로 칸을 가리킨다.
    df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
    # 병합으로 생긴 빈칸만 채운다. 원래 비어 있던 칸은 그대로 둔다.
    _fill_merged_cells(df, file_path, sheet_name)
    source_path = file_path.as_posix()

    chunks = []
    # 모든 행을 위에서부터 훑으며 주차 블록의 시작을 찾는다.
    for row_index in range(len(df)):
        # "시작시간" 줄이 주차 블록의 날짜 줄이다. 바로 위 줄이 "17주차".
        if df.iat[row_index, _TIME_START_COL] != "시작시간":
            continue
        week = _clean_text(df.iat[row_index - 1, _TIME_START_COL])
        # 월~금(E~I열) 다섯 열을 하루씩 청크로 만든다.
        for col in range(_FIRST_DAY_COL, _LAST_DAY_COL + 1):
            text, end_row = _day_text(df, row_index, col, week)
            # 하루 = 날짜 칸부터 마지막 정보 칸까지. 예) 시트1!I275:I285
            location = (
                f"{sheet_name}!{_cell_name(row_index, col)}"
                f":{_cell_name(end_row, col)}"
            )
            chunks.append(
                _make_chunk(
                    document_id,
                    len(chunks) + 1,
                    text,
                    source_path,
                    location,
                )
            )

    # 시간표 옆의 제적 기준표는 마지막 청크 하나로 넣는다.
    # 주의: 이 부분은 위 반복문이 모두 끝난 뒤 한 번만 실행해야 한다.
    # 반복문 안에 들어가면 1주차만 읽고 바로 return 해 버린다.
    dismissal = _dismissal_text(df)
    if dismissal is not None:
        text, first_row, last_row = dismissal
        # 표 영역 = K열 첫 행부터 L열 마지막 행까지. 예) 시트1!K4:L13
        location = (
            f"{sheet_name}!{_cell_name(first_row, _PERIOD_COL)}"
            f":{_cell_name(last_row, _RULE_COL)}"
        )
        chunks.append(
            _make_chunk(
                document_id,
                len(chunks) + 1,
                text,
                source_path,
                location,
            )
        )
    return chunks


def load_excel_chunks(file_path: str, document_id: str) -> list[dict]:
    """xlsx 파일을 읽어 청크 목록을 만든다.

    xlsx에는 md 같은 "문서 ID:" 머리말이 없어서 문서 ID를 인자로 받는다.
    """
    path = Path(file_path)
    # 첫 번째 시트를 기준으로 읽는다. 두 원문 모두 시트가 하나다.
    # ExcelFile(...).sheet_names → ["시트1"] 같은 시트 이름 목록
    sheet_name = pd.ExcelFile(path).sheet_names[0]
    df = pd.read_excel(path, sheet_name=sheet_name, header=None)
    # B열에 "시작시간"이 있으면 주차별 격자 시간표, 없으면 일반 표다.
    # (df[열] == 값).any() → 한 칸이라도 같으면 True
    if (df[_TIME_START_COL] == "시작시간").any():
        chunks = _load_weekly_timetable(path, document_id, sheet_name)
    else:
        chunks = _load_table(path, document_id, sheet_name)
    # 몇 개의 청크가 만들어졌는지 로그로 남겨 적재 결과를 확인한다.
    logger.info(
        "[excel_loader] %s (%s) -> 청크 %d개",
        path.name,
        document_id,
        len(chunks),
    )
    return chunks


def main() -> None:
    """명령행으로 받은 xlsx 파일의 청크를 JSON으로 출력한다.

    사용법: python -m kant_agent.document_indexing.excel_loader
            <xlsx 경로> <문서 ID>
    """
    # sys.argv[0]은 실행한 모듈 이름, [1]·[2]가 넘겨받은 값이다.
    chunks = load_excel_chunks(sys.argv[1], sys.argv[2])
    # Windows 콘솔 기본값(cp949)은 이모지·일부 한글을 못 써서 UTF-8로 고정한다.
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(chunks, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
