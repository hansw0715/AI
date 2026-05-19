"""피격 파티클 — 좀비 부위 hit 시 hit point에서 사방으로 퍼지는 작은 카드들.

부위별로 개수/크기/색/속도/수명이 다름.
실제 Panda3D ParticleEffect 안 씀 — CardMaker + 매 프레임 task로 단순 시뮬레이션
(설정 파일 .ptf 부담 회피).
"""

import math
import random

from panda3d.core import (
    BillboardEffect,
    CardMaker,
    ClockObject,
    TransparencyAttrib,
    Vec3,
)


_clock = ClockObject.getGlobalClock()

# 부위 카테고리별 파라미터 ---------------------------------------
# "arm"/"leg" 카테고리는 left_/right_ 두 부위가 공유.
PARTICLE_COUNT = {"head": 18, "body": 10, "arm": 5, "leg": 5}
PARTICLE_SIZE = {"head": 0.10, "body": 0.07, "arm": 0.05, "leg": 0.05}

PARTICLE_COLOR_HEAD_PRIMARY = (1.0, 1.0, 1.0, 1.0)        # 흰색 플래시
PARTICLE_COLOR_HEAD_SECONDARY = (0.7, 0.05, 0.05, 1.0)    # 진한 빨강
PARTICLE_COLOR_BODY = (0.7, 0.05, 0.05, 1.0)
PARTICLE_COLOR_LIMB = (0.5, 0.03, 0.03, 1.0)              # 어두운 빨강

PARTICLE_SPEED_RANGE = {
    "head": (2.5, 4.5),
    "body": (1.5, 3.0),
    "arm": (1.0, 2.0),
    "leg": (1.0, 2.0),
}
PARTICLE_LIFETIME = {"head": 0.45, "body": 0.30, "arm": 0.25, "leg": 0.25}
PARTICLE_GRAVITY = 4.0      # m/s^2, -Z 방향. Panda3D Z-up.
_MAX_DT = 1.0 / 30.0        # 첫 프레임 dt 폭주 시 파티클이 멀리 튀는 거 방지


def _category_from_part(part_name):
    """hit_part 이름을 파티클 파라미터 키 ("head"/"body"/"arm"/"leg") 로 매핑."""
    if part_name is None:
        return "body"
    if part_name == "head":
        return "head"
    if part_name == "body":
        return "body"
    if "arm" in part_name:
        return "arm"
    if "leg" in part_name:
        return "leg"
    return "body"


def _pick_color(category, index):
    if category == "head":
        # 헤드샷은 흰 플래시 + 빨강 혼합 (인덱스 짝/홀로 절반씩 배치).
        return PARTICLE_COLOR_HEAD_PRIMARY if index % 2 == 0 else PARTICLE_COLOR_HEAD_SECONDARY
    if category == "body":
        return PARTICLE_COLOR_BODY
    return PARTICLE_COLOR_LIMB


def _random_unit_sphere_direction():
    """구 전체 표면에 균일 분포된 단위 방향 벡터."""
    theta = random.uniform(0.0, 2.0 * math.pi)
    z = random.uniform(-1.0, 1.0)                 # cosine(phi) 균일 → 균등 분포
    horizontal = math.sqrt(max(0.0, 1.0 - z * z))
    return Vec3(horizontal * math.cos(theta), horizontal * math.sin(theta), z)


def spawn_hit_particles(base, world_pos, hit_part):
    """world_pos 에서 부위별 파라미터로 파티클을 생성. 매 프레임 task로 진행/정리."""
    category = _category_from_part(hit_part)
    count = PARTICLE_COUNT[category]
    size = PARTICLE_SIZE[category]
    speed_min, speed_max = PARTICLE_SPEED_RANGE[category]
    lifetime = PARTICLE_LIFETIME[category]

    particles = []
    for i in range(count):
        cm = CardMaker(f"hit_particle_{category}_{i}")
        cm.setFrame(-size / 2, size / 2, -size / 2, size / 2)
        p_np = base.render.attachNewNode(cm.generate())
        p_np.setPos(world_pos)
        # 항상 카메라 향하게 — 카드의 단면이 옆에서 안 보이도록.
        p_np.setEffect(BillboardEffect.makePointEye())
        p_np.setTransparency(TransparencyAttrib.MAlpha)
        p_np.setLightOff(1)
        p_np.setColor(*_pick_color(category, i))

        direction = _random_unit_sphere_direction()
        speed = random.uniform(speed_min, speed_max)
        velocity = direction * speed
        particles.append({"np": p_np, "velocity": velocity, "age": 0.0})

    # 매 프레임 진행 — 모든 파티클이 죽으면 task 종료.
    task_name = f"hit_particles_{id(particles)}"

    def _update(task, _particles=particles, _lifetime=lifetime):
        dt = min(_clock.getDt(), _MAX_DT)
        all_dead = True
        for p in _particles:
            if p["np"].isEmpty():
                continue
            p["age"] += dt
            if p["age"] >= _lifetime:
                p["np"].removeNode()
                continue
            all_dead = False
            # 위치 = 위치 + v*dt
            p["np"].setPos(p["np"].getPos() + p["velocity"] * dt)
            # 중력
            p["velocity"].z -= PARTICLE_GRAVITY * dt
            # 수명 후반(50%)부터 알파 페이드.
            t = p["age"] / _lifetime
            if t > 0.5:
                p["np"].setAlphaScale(max(0.0, 1.0 - (t - 0.5) * 2.0))
        if all_dead:
            return task.done
        return task.cont

    base.taskMgr.add(_update, task_name)
