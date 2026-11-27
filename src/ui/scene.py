"""움직이는 서고 배경 (램프 불빛, 빛가루, 보라 안개, 숨 쉬는 다크타니).

배경 그림(archive.webp)과 같은 비율의 상자(.scene-art)를 화면에 꽉 차게(cover) 놓고,
그 안에 효과를 % 위치로 겹친다. 위치 숫자는 원본 그림(1672x941)의 픽셀 좌표다.
st.html은 SVG와 style 속성을 지우므로 div와 클래스별 CSS 규칙만 쓴다.
(교안에 없음: CSS 애니메이션)
"""

import random

WIDTH, HEIGHT = 1672, 941

# 그림 속 램프 전등갓 위치 (x, y, 빛 지름)
LAMPS = [
    (651, 565, 200),  # 책상 램프
    (129, 538, 150),  # 왼쪽 책상 램프
    (180, 78, 80),
    (909, 58, 80),
    (1322, 103, 90),
    (708, 165, 70),
    (529, 257, 80),
    (1369, 317, 90),
    (375, 383, 70),
    (849, 405, 70),
]

# 다크타니만 오려 낸 그림(darktani_cut.png)의 위치와 크기 (x, y, 너비, 높이)
TANI = (190, 380, 350, 288)

# 의자 등받이 윗부분만 오려 낸 그림(chair_front.png)의 위치와 크기
CHAIR = (150, 600, 450, 160)


def _box(x: float, y: float, w: float, h: float) -> str:
    """그림 픽셀 좌표를 .scene-art 안의 % 위치로 바꾼다."""
    return (
        f"left:{x / WIDTH * 100:.2f}%;top:{y / HEIGHT * 100:.2f}%;"
        f"width:{w / WIDTH * 100:.2f}%;height:{h / HEIGHT * 100:.2f}%;"
    )


def _lamps() -> tuple[str, str]:
    rng = random.Random(7)
    html, css = [], []
    for i, (x, y, d) in enumerate(LAMPS):
        duration = rng.uniform(2.8, 5.5)
        delay = -rng.uniform(0, duration)
        html.append(f'<div class="lamp lamp-{i}"></div>')
        css.append(
            f".lamp-{i}{{{_box(x - d / 2, y - d / 2, d, d)}"
            f"animation-duration:{duration:.1f}s;animation-delay:{delay:.1f}s}}"
        )
    return "".join(html), "".join(css)


def _dust(count: int = 45) -> tuple[str, str]:
    rng = random.Random(42)
    html, css = [], []
    for i in range(count):
        x = rng.uniform(0, WIDTH)
        y = rng.uniform(HEIGHT * 0.25, HEIGHT)
        size = rng.uniform(2.5, 6)
        color = rng.choice(["#ffe7a8", "#ffd27a", "#e7c4ff"])
        duration = rng.uniform(9, 18)
        delay = -rng.uniform(0, duration)
        drift = rng.uniform(-40, 40)
        html.append(f'<div class="dust dust-{i}"></div>')
        css.append(
            f".dust-{i}{{{_box(x, y, size, size)}background:{color};"
            f"box-shadow:0 0 8px 2px {color};--drift:{drift:.0f}px;"
            f"animation-duration:{duration:.1f}s;animation-delay:{delay:.1f}s}}"
        )
    return "".join(html), "".join(css)


def tani_html(tilt: str = "") -> str:
    """다크타니와 의자 앞부분. 배경과 따로 그려서 이 부분만 다시 그릴 수 있다.

    tilt에 "tilt-a" 또는 "tilt-b"를 주면 고개를 한 번 갸우뚱한다.
    두 이름은 같은 동작이며, 이름이 바뀌어야 애니메이션이 다시 재생되므로 번갈아 쓴다.
    """
    return f"""
    <div class="scene" aria-hidden="true">
      <div class="scene-art">
        <div class="tani-wrap {tilt}"><div class="tani"></div></div>
        <div class="chair-front"></div>
      </div>
    </div>
    """


def effects_html() -> str:
    """보라 안개, 램프 불빛, 빛가루. 다크타니·의자보다 위에 겹치도록 tani_html() 뒤에 그린다.

    (의자 그림이 안개를 가리면 의자 상자 테두리가 일자 선으로 보인다)
    """
    lamps_html, _ = _lamps()
    dust_html, _ = _dust()
    return f"""
    <div class="scene" aria-hidden="true">
      <div class="scene-art">
        <div class="mist mist-1"></div>
        <div class="mist mist-2"></div>
        <div class="mist mist-3"></div>
        {lamps_html}
        {dust_html}
      </div>
    </div>
    """


def scene_html() -> str:
    """배경 그림과 모든 효과의 CSS. 순서: scene_html → tani_html → effects_html."""
    _, lamps_css = _lamps()
    _, dust_css = _dust()
    tani_box = _box(*TANI)
    return f"""
    <div class="scene" aria-hidden="true">
      <div class="scene-art scene-bg"></div>
    </div>
    <style>
    .stApp {{ background: transparent; }}
    body {{ background: #21121d; }}
    .scene {{ position: fixed; inset: 0; z-index: -1; overflow: hidden; pointer-events: none; }}

    /* 그림 비율(1672:941)을 지키며 화면을 꽉 채운다 (cover와 같은 계산) */
    .scene-art {{
      position: absolute;
      left: 50%;
      top: 50%;
      width: max(100vw, 100vh * {WIDTH} / {HEIGHT});
      height: max(100vh, 100vw * {HEIGHT} / {WIDTH});
      transform: translate(-50%, -50%);
    }}
    /* 다크타니를 지운 배경. 다크타니는 tani_html()이 따로 겹친다 */
    .scene-bg {{
      background: url("app/static/archive_clean.webp") center / 100% 100% no-repeat;
    }}
    .scene-art > div {{ position: absolute; }}

    /* 램프 불빛: 은은하게 깜빡임 */
    .lamp {{
      border-radius: 50%;
      background: radial-gradient(circle, #ffd890a6 0%, #ffb04a2e 45%, #ffb04a00 70%);
      mix-blend-mode: screen;
      animation: lamp-flicker ease-in-out infinite;
    }}
    {lamps_css}
    @keyframes lamp-flicker {{
      0%, 100% {{ opacity: 0.7; }}
      20% {{ opacity: 0.95; }}
      24% {{ opacity: 0.35; }}
      28% {{ opacity: 0.9; }}
      60% {{ opacity: 0.6; }}
      75% {{ opacity: 1; }}
    }}

    /* 빛가루: 아래에서 위로 떠오르며 사라짐 */
    .dust {{ border-radius: 50%; opacity: 0; animation: dust-float linear infinite; }}
    {dust_css}
    @keyframes dust-float {{
      0% {{ transform: translate(0, 0); opacity: 0; }}
      15% {{ opacity: 0.9; }}
      85% {{ opacity: 0.6; }}
      100% {{ transform: translate(var(--drift), -160px); opacity: 0; }}
    }}

    /* 보라 안개: 좌우로 천천히 흐름 */
    .mist {{
      border-radius: 50%;
      filter: blur(45px);
      animation: mist-flow ease-in-out infinite alternate;
    }}
    .mist-1 {{ {_box(-120, 710, 1040, 220)} background: #8b4fd638; animation-duration: 28s; }}
    .mist-2 {{ {_box(690, 640, 1120, 240)} background: #b25ad833; animation-duration: 36s; animation-delay: -12s; }}
    .mist-3 {{ {_box(370, 330, 960, 180)} background: #6d3fb826; animation-duration: 44s; animation-delay: -20s; }}
    @keyframes mist-flow {{
      from {{ transform: translateX(-12%); }}
      to {{ transform: translateX(12%); }}
    }}

    /* 다크타니: 천천히 숨 쉬고 테두리 빛이 커졌다 작아짐 */
    .tani-wrap {{ {tani_box} transform-origin: 50% 100%; }}
    .scene-art .tani {{
      position: absolute;
      inset: 0;
      background: url("app/static/darktani_cut.png") center / 100% 100% no-repeat;
      transform-origin: 50% 100%;
      animation: tani-breathe 4.8s ease-in-out infinite;
    }}
    @keyframes tani-breathe {{
      0%, 100% {{ transform: scale(1, 1); filter: drop-shadow(0 0 4px #e9a8ff88); }}
      50% {{ transform: scale(1.015, 1.035); filter: drop-shadow(0 0 16px #e9a8ffdd); }}
    }}

    /* 근거 없음 답변이 오면 고개를 한 번 갸우뚱 (tilt-a, tilt-b는 같은 동작) */
    .tani-wrap.tilt-a {{ animation: tani-tilt-a 2.6s ease-in-out 1; }}
    .tani-wrap.tilt-b {{ animation: tani-tilt-b 2.6s ease-in-out 1; }}
    @keyframes tani-tilt-a {{
      0%, 100% {{ transform: rotate(0deg); }}
      18%, 58% {{ transform: rotate(9deg); }}
      72% {{ transform: rotate(-2deg); }}
    }}
    @keyframes tani-tilt-b {{
      0%, 100% {{ transform: rotate(0deg); }}
      18%, 58% {{ transform: rotate(9deg); }}
      72% {{ transform: rotate(-2deg); }}
    }}

    /* 의자 앞부분: 기울어진 다크타니가 의자 위로 튀어나오지 않게 덮는다 */
    .chair-front {{
      {_box(*CHAIR)}
      background: url("app/static/chair_front.png") center / 100% 100% no-repeat;
    }}

    /* 애니메이션 줄이기 설정이면 멈춘 배경을 보여 준다 */
    @media (prefers-reduced-motion: reduce) {{
      .scene * {{ animation: none !important; }}
    }}
    </style>
    """
