"""충돌 설정 헬퍼.

이 단계에서는 Bullet 없이 Panda3D 내장 충돌 시스템만 사용한다.
플레이어는 발 밑으로 수직 CollisionRay 하나만 쏴서 지면 높이를 읽고
중력 적용 후 그 위로 스냅하는 방식으로 바닥에 서있게 한다.
"""

from panda3d.core import (
    BitMask32,
    CollisionNode,
    CollisionRay,
)


GROUND_MASK = BitMask32.bit(1)
HITTABLE_MASK = BitMask32.bit(2)
# 좀비 전용 비트 — 환경과 분리해서 raycast가 둘을 구분할 수 있게 함.
# 권총 raycast는 from-mask에 HITTABLE_MASK | ZOMBIE_MASK를 사용하고,
# entry의 PythonTag("zombie")로 어느 좀비를 맞췄는지 역추적한다.
ZOMBIE_MASK = BitMask32.bit(3)


def make_ground_ray(parent_node, traverser, handler, name="player_ground_ray", origin_z=200.0):
    """parent_node에 아래로 향하는 CollisionRay를 부착하고 traverser에 등록.

    origin_z를 충분히 크게 잡아 플레이어가 어디로 떨어져도 ray가 항상 지형 위에서
    시작하도록 한다 (터널링 후 복구 가능). 발 밑 거리는 surface point의 절대 Z로 판단.
    """
    ray = CollisionRay()
    ray.setOrigin(0, 0, origin_z)
    ray.setDirection(0, 0, -1)

    cnode = CollisionNode(name)
    cnode.addSolid(ray)
    cnode.setFromCollideMask(GROUND_MASK)
    cnode.setIntoCollideMask(BitMask32.allOff())

    ray_np = parent_node.attachNewNode(cnode)
    traverser.addCollider(ray_np, handler)
    return ray_np
