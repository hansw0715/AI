"""월드 공간 데미지 숫자 — 좀비 피격 시 hit point 근처에 빨간 숫자가 잠깐 떴다가
위로 떠오르며 페이드 아웃.

`effects.spawn_hit_particles` 와 동일 패턴:
  - 매 프레임 task 로 위치/알파 갱신 후 수명 종료 시 removeNode
  - BillboardEffect.makePointEye() 로 카드가 항상 카메라를 향함
  - setLightOff(1) 로 씬 라이팅 무시 (좀비 체력바와 같은 패턴)
  - 첫 프레임 dt 폭주 클램프 (_MAX_DT)

부위별 강조:
  - 일반 hit  → 빨강
  - 헤드샷    → 노란빛 빨강 + 크기 1.3 배
"""

import random

from panda3d.core import (
    BillboardEffect,
    ClockObject,
    TextNode,
    TransparencyAttrib,
    Vec3,
)


_clock = ClockObject.getGlobalClock()

DAMAGE_TEXT_COLOR = (1.0, 0.2, 0.2, 1.0)         # 일반 빨강
HEADSHOT_TEXT_COLOR = (1.0, 0.85, 0.2, 1.0)      # 헤드샷 — 노란빛 빨강
DAMAGE_TEXT_SCALE = 0.6                          # TextNode 는 기본이 작아서 키움
HEADSHOT_SCALE_MULT = 1.3                        # 헤드샷 크기 강조 배수
DAMAGE_TEXT_JITTER = 0.15                        # spawn 시 X/Z ± 랜덤 오프셋 (m)
DAMAGE_TEXT_RISE = 0.8                           # 수명 동안 위로 떠오르는 거리 (m)
DAMAGE_TEXT_HOLD_SEC = 0.3                       # 풀 알파 유지 시간 (초)
DAMAGE_TEXT_FADE_SEC = 0.4                       # 페이드 시간 (초)
_MAX_DT = 1.0 / 30.0


def spawn_damage_number(base, world_pos, damage_value, hit_part):
    """world_pos 근처에 데미지 숫자 1개 spawn. 매 프레임 task 로 떠오름 + 페이드 후 제거.

    headshot 만 색/크기를 강조해 다른 부위와 구분.
    spawn 좌표 X/Z 에 ± DAMAGE_TEXT_JITTER jitter — 연사 시 숫자가 같은 위치에
    겹쳐 보이지 않게 분산.
    """
    is_head = hit_part == "head"
    color = HEADSHOT_TEXT_COLOR if is_head else DAMAGE_TEXT_COLOR
    scale = DAMAGE_TEXT_SCALE * (HEADSHOT_SCALE_MULT if is_head else 1.0)

    text_node = TextNode("damage_number")
    text_node.setText(str(int(damage_value)))
    text_node.setAlign(TextNode.ACenter)
    text_node.setTextColor(*color)

    text_np = base.render.attachNewNode(text_node)
    start_pos = Vec3(
        world_pos.x + random.uniform(-DAMAGE_TEXT_JITTER, DAMAGE_TEXT_JITTER),
        world_pos.y,
        world_pos.z + random.uniform(-DAMAGE_TEXT_JITTER, DAMAGE_TEXT_JITTER),
    )
    text_np.setPos(start_pos)
    text_np.setScale(scale)
    text_np.setEffect(BillboardEffect.makePointEye())
    text_np.setLightOff(1)
    text_np.setTransparency(TransparencyAttrib.MAlpha)

    total = DAMAGE_TEXT_HOLD_SEC + DAMAGE_TEXT_FADE_SEC
    state = {"age": 0.0, "np": text_np, "start_pos": start_pos}
    task_name = f"damage_number_{id(state)}"

    def _update(task, _state=state, _total=total):
        np = _state["np"]
        if np.isEmpty():
            return task.done
        dt = min(_clock.getDt(), _MAX_DT)
        _state["age"] += dt
        age = _state["age"]

        # 위로 떠오름 — 전체 수명에 걸쳐 0 → DAMAGE_TEXT_RISE 선형.
        sp = _state["start_pos"]
        rise = DAMAGE_TEXT_RISE * min(1.0, age / _total)
        np.setPos(sp.x, sp.y, sp.z + rise)

        # 페이드 — HOLD 동안 풀 알파, FADE 동안 선형 감소.
        if age < DAMAGE_TEXT_HOLD_SEC:
            alpha = 1.0
        elif age < _total:
            alpha = 1.0 - (age - DAMAGE_TEXT_HOLD_SEC) / DAMAGE_TEXT_FADE_SEC
        else:
            np.removeNode()
            return task.done
        np.setAlphaScale(max(0.0, alpha))
        return task.cont

    base.taskMgr.add(_update, task_name)
