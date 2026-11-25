from pathlib import Path

import requests
import streamlit as st

API_URL = "http://127.0.0.1:8000/v1/chatbot/ask"

BOT_NAME = "어둠의 에이타니"
BOT_AVATAR = Path(__file__).parent / "assets" / "bot.png"

st.title("어둠의 에이타니 챗봇")

# 말풍선 모양 (key= 로 만든 st-key-... 클래스만 꾸민다)
st.html(
    """
    <style>
    div[class*="st-key-user-msg"] {
        background: #FEE500;
        color: #191919;
        border-radius: 16px;
        padding: 8px 14px;
        max-width: 70%;
        width: fit-content !important;
        margin-left: auto;
    }
    div[class*="st-key-bot-msg"] {
        background: #FFFFFF;
        color: #191919;
        border: 1px solid #E5E7EB;
        border-radius: 16px;
        padding: 8px 14px;
        max-width: 80%;
        width: fit-content !important;
    }
    div[class*="st-key-bot-msg-no_evidence"] { background: #EEF4FF; }
    div[class*="st-key-bot-msg-error"] { background: #FDECEC; }
    </style>
    """
)

# 대화 기록을 저장할 메모리 공간(messages)이 없다면 새로 만든다.
if "messages" not in st.session_state:
    st.session_state["messages"] = []


# 답변 아래에 근거 목록을 표시한다.
def show_citations(citations: list[dict]) -> None:
    if not citations:
        return
    with st.expander("참고 자료 보기"):
        for c in citations:
            st.write(
                f"[{c['ref_number']}] {c['document_id']} · "
                f"{c['source_location']} ({c['source_path']})"
            )


# 말풍선 이미지 - user
def show_user(idx: int, msg: dict) -> None:
    with st.container(key=f"user-msg-{idx}"):
        st.markdown(msg["content"], width="content")


# 말풍선 이미지 - chatbot
def show_bot(idx: int, msg: dict) -> None:
    with st.chat_message("assistant", avatar=BOT_AVATAR):
        st.caption(BOT_NAME)
        key = f"bot-msg-{msg['kind']}-{idx}"
        with st.container(key=key):
            st.markdown(msg["content"], width="content")
            show_citations(msg.get("citations", []))


# API에 질문하고, 화면에 그릴 챗봇 메세지를 만든다.
def ask_api(question: str) -> dict:
    try:
        res = requests.post(API_URL, json={"question": question}, timeout=60)
        body = res.json()
    except requests.RequestException:
        body = {
            "success": False,
            "code": "CONNECTION_ERROR",
            "message": "API 서버에 연결할 수 없습니다.",
        }

    if body.get("success"):
        data = body["data"]
        return {
            "role": "assistant",
            "kind": data["status"],
            "content": data["answer"],
            "citations": data["citations"],
        }
    return {
        "role": "assistant",
        "kind": "error",
        "content": f"오류: {body.get('message')} ({body.get('code')})",
        "citations": [],
    }


# 메시지 종류에 맞는 말풍선으로 그린다.
def show_message(idx: int, msg: dict) -> None:
    if msg["role"] == "user":
        show_user(idx, msg)
    else:
        show_bot(idx, msg)

# 메모리에 저장된 이전 대화 기록들을 화면에 모두 순서대로 그린다.
for i, msg in enumerate(st.session_state["messages"]):
    show_message(i, msg)

if prompt := st.chat_input(f"{BOT_NAME}에게 물어보세요.", max_chars=500):
    prompt = prompt.strip()
    if prompt:
        messages = st.session_state["messages"]

        user_msg = {"role": "user", "content": prompt}
        messages.append(user_msg)
        show_message(len(messages) - 1, user_msg)

        with st.spinner("답변을 준비하는 중..."):
            bot_msg = ask_api(prompt)
        messages.append(bot_msg)
        show_message(len(messages) - 1, bot_msg)