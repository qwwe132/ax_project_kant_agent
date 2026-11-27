from pathlib import Path

import httpx
import streamlit as st

from scene import effects_html, scene_html, tani_html

API_URL = "http://127.0.0.1:8000/v1/chatbot/ask"

BOT_NAME = "어둠의 마왕 다크타니"
BOT_AVATAR = Path(__file__).parent / "assets" / "bot.gif"

st.set_page_config(page_title=BOT_NAME, layout="wide")

# 대화 기록을 저장할 메모리 공간(messages)이 없다면 새로 만든다.
if "messages" not in st.session_state:
    st.session_state["messages"] = []


# 마지막 답변이 근거 없음이면 다크타니가 고개를 갸우뚱한다.
# 답변마다 tilt-a, tilt-b를 번갈아 줘야 연속으로 근거 없음이 와도 다시 움직인다.
def tani_tilt(messages: list[dict]) -> str:
    if messages and messages[-1].get("kind") == "no_evidence":
        return "tilt-a" if len(messages) // 2 % 2 else "tilt-b"
    return ""


# 움직이는 배경 - scene.py (배경 → 다크타니·의자 → 안개·불빛·빛가루 순서로 겹친다)
st.html(scene_html())
# 다크타니는 따로 그린다. 답변이 오면 이 자리만 다시 그린다.
tani_slot = st.empty()
tani_slot.html(tani_html(tani_tilt(st.session_state["messages"])))
# 안개·램프 불빛·빛가루는 다크타니와 의자 위에 겹친다.
st.html(effects_html())

# 오른쪽 대화 창과 말풍선 모양 (key= 로 만든 st-key-... 클래스만 꾸민다)
# (교안에 없음: Streamlit 정적 파일 서빙과 CSS. 색은 src/ui/library/index.html 기준)
st.html("""
    <style>
    [data-testid="stHeader"] { background: transparent; }

    .st-key-chat-panel {
        width: 50% !important;
        margin-left: auto;
        margin-top: 3vh;
        padding: 16px 24px;
        border: 1px solid #dba7d19c;
        border-radius: 32px;
        background: linear-gradient(125deg, #55354cbd, #362030d9 65%, #55334ac9);
        backdrop-filter: blur(12px);
        box-shadow: 0 16px 52px #130a1455;
    }

    div[class*="st-key-user-msg"] {
        background: #e0b8f7;
        color: #291637;
        border-radius: 20px 20px 5px 20px;
        padding: 8px 14px;
        max-width: 75%;
        width: fit-content !important;
        margin-left: auto;
    }
    div[class*="st-key-bot-msg"] {
        background: #643768c9;
        color: #fff4ff;
        border: 1px solid #ad77b795;
        border-radius: 20px 20px 20px 5px;
        padding: 8px 14px;
        max-width: 90%;
        width: fit-content !important;
    }
    div[class*="st-key-bot-msg-no_evidence"] { background: #3f3a6bc9; }
    div[class*="st-key-bot-msg-error"] { background: #6b2f3fc9; }
    div[class*="st-key-bot-msg"] [data-testid="stExpander"] summary,
    div[class*="st-key-bot-msg"] [data-testid="stExpander"] summary * {
        background: transparent;
        color: #e6c8ed;
    }

    @media (max-width: 800px) {
        .st-key-chat-panel { width: 100% !important; padding: 12px 14px; }
        .st-key-chat-panel h1 { font-size: 1.6rem; }
    }
    </style>
    """)


# 마크다운에서 ~글자~ 가 취소선이 되지 않도록 ~ 를 글자 그대로 표시한다.
# (예: 09:00~13:00, 13:00~14:00 이 취소선으로 깨지는 문제)
def plain_tilde(text: str) -> str:
    return text.replace("~", r"\~")


# 답변 아래에 근거 목록을 표시한다.
def show_citations(citations: list[dict]) -> None:
    if not citations:
        return
    with st.expander("참고 자료 보기"):
        for c in citations:
            title = c.get("title") or c["document_id"]
            url = c.get("source_url")
            name = f"[{title}]({url})" if url else title
            st.markdown(f"[{c['ref_number']}] {name} · {c['source_location']}")


# 말풍선 이미지 - user
def show_user(idx: int, msg: dict) -> None:
    with st.container(key=f"user-msg-{idx}"):
        st.markdown(plain_tilde(msg["content"]), width="content")


# 말풍선 이미지 - chatbot
def show_bot(idx: int, msg: dict) -> None:
    with st.chat_message("assistant", avatar=BOT_AVATAR):
        key = f"bot-msg-{msg['kind']}-{idx}"
        with st.container(key=key):
            st.markdown(plain_tilde(msg["content"]), width="content")
            show_citations(msg.get("citations", []))


# 오류 말풍선용 챗봇 메시지를 만든다.
def error_message(code: str, message: str) -> dict:
    return {
        "role": "assistant",
        "kind": "error",
        "content": f"오류: {message} ({code})",
        "citations": [],
    }


# API에 질문하고, 화면에 그릴 챗봇 메세지를 만든다.
def ask_api(question: str) -> dict:
    # 1) 서버에 연결
    try:
        with httpx.Client(timeout=60) as client:
            res = client.post(API_URL, json={"question": question})
    except httpx.RequestError:
        return error_message("CONNECTION_ERROR", "API 서버에 연결할 수 없습니다.")

    # 2) 응답을 JSON으로 읽기 (HTML 같은 다른 응답이면 실패)
    try:
        body = res.json()
    except ValueError:
        return error_message("INVALID_RESPONSE", "API 응답 형식이 올바르지 않습니다.")

    # 3) 응답이 객체(DICT)인지 확인 (null, 리스트 등 차단)
    if not isinstance(body, dict):
        return error_message("INVALID_RESPONSE", "API 응답 형식이 올바르지 않습니다.")

    # 4) API가 보낸 실패 응답 (검증 실패, 서버 오류 등)
    if not body.get("success"):
        return error_message(body.get("code"), body.get("message"))

    # 5) 성공 응답에 필요한 값이 다 있는지 확인
    data = body.get("data")
    if (
        not isinstance(data, dict)
        or data.get("status") not in ("ok", "no_evidence", "chat")
        or not isinstance(data.get("answer"), str)
        or not isinstance(data.get("citations"), list)
    ):
        return error_message("INVALID_RESPONSE", "API 응답 형식이 올바르지 않습니다.")

    return {
        "role": "assistant",
        "kind": data["status"],
        "content": data["answer"],
        "citations": data["citations"],
    }


# 메시지 종류에 맞는 말풍선으로 그린다.
def show_message(idx: int, msg: dict) -> None:
    if msg["role"] == "user":
        show_user(idx, msg)
    else:
        show_bot(idx, msg)


# 오른쪽 대화 창: 제목 + 대화 기록(스크롤) + 입력창
with st.container(key="chat-panel"):
    with st.container(horizontal=True, vertical_alignment="center", wrap=False):
        st.image(BOT_AVATAR, width=64)
        st.title(BOT_NAME, anchor=False)

    # 높이를 고정하면 내용이 넘칠 때 이 안에서만 스크롤된다.
    # autoscroll=True: 새 메시지가 오면 자동으로 맨 아래로 내린다.
    log = st.container(height=500, border=False, autoscroll=True, key="chat-log")

    # 컨테이너 안에 넣으면 입력창이 화면 맨 아래가 아니라 창 안에 붙는다.
    prompt = st.chat_input("질문을 입력하세요", max_chars=500)

# 메모리에 저장된 이전 대화 기록들을 대화 창 안에 순서대로 그린다.
with log:
    for i, msg in enumerate(st.session_state["messages"]):
        show_message(i, msg)

if prompt and prompt.strip():
    prompt = prompt.strip()
    messages = st.session_state["messages"]

    with log:
        user_msg = {"role": "user", "content": prompt}
        messages.append(user_msg)
        show_message(len(messages) - 1, user_msg)

        with st.spinner("기록을 살피는 중..."):
            bot_msg = ask_api(prompt)
        messages.append(bot_msg)
        show_message(len(messages) - 1, bot_msg)

    tani_slot.html(tani_html(tani_tilt(messages)))
