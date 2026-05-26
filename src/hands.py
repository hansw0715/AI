"""1인칭 손 모델 — 외부 glTF Gloved Hand (CC-BY, J-Toastie) + 박스 폴백.

hand_root (self.np) 원점 = 손목 위치. 손-팔 모델은 self.np 의 자식으로 reparent
되고, 사용자 측 (weapons.py) 는 self.np 의 setPos/setHpr/wrtReparentTo/setColorScale
만 만진다. 손목 pivot 일치가 가장 중요 — 모델의 손목이 self.np 원점에 오도록 모델
자체에 setPos 보정.

축 컨벤션 (self.np-local):
  +Y = 손가락 방향 (전방)
  +Z = 손등 (위)
  +X = 엄지 바깥쪽 (오른손 기준)

weapons.py 의 RIGHT_HAND_REST_HPR = (15, -25, 0) 등이 이 축 가정으로 calibration
되어 있어서 외부 모델 import 후 setHpr 로 위 축에 맞춰야 함.

USE_EXTERNAL_MODEL=False 또는 glb 파일 로드 실패 시 자동으로 박스 폴백 (fist +
forearm + sleeve 조립).
"""

import os

import gltf
from direct.actor.Actor import Actor
from panda3d.core import (
    Filename,
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexReader,
    Material,
    NodePath,
    TransparencyAttrib,
    Vec3,
    Vec4,
)


HAND_COLOR = Vec4(0.75, 0.55, 0.45, 1)
SLEEVE_COLOR = Vec4(0.25, 0.30, 0.32, 1)


# PBR Material 정의 — 박스 폴백 경로 전용. glb 머티리얼이 있으면 그대로 두고
# 어두우면 강제 적용 (calibration 단계에서 결정).
_SKIN_MAT = Material("skin")
_SKIN_MAT.setBaseColor(HAND_COLOR)
_SKIN_MAT.setMetallic(0.0)
_SKIN_MAT.setRoughness(0.75)

_SLEEVE_MAT = Material("sleeve")
_SLEEVE_MAT.setBaseColor(SLEEVE_COLOR)
_SLEEVE_MAT.setMetallic(0.0)
_SLEEVE_MAT.setRoughness(0.90)


# 외부 손/팔 모델 — DJMaesen FPS Arms (Sketchfab, CC-BY 4.0). scene.gltf + scene.bin +
# textures/ 셋트라 수동 다운로드 필요.
_ARM_GLB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "models", "arms", "scene.gltf",
)
USE_EXTERNAL_MODEL = True

# DJMaesen 모델은 양손 통합 mesh + L_/R_ 본 분리 스켈레톤. 정점 X 부호로 mesh 를
# 두 GeomNode 로 split → 각 Hand 인스턴스에 해당 손/팔 부분만 부착 → 4 팔 없이
# 양손 독립 setPos/setHpr 가능. _split_dual_arm_geom 헬퍼가 한 번만 실행되고 결과는
# 모듈 전역 _SPLIT_GEOMS 에 캐시 (좌/우 두 노드).
_SPLIT_GEOMS: dict[str, NodePath] = {}

# ---- 외부 모델 calibration (스크린샷 보면서 반복 튜닝) ----
# 모델 자체의 축을 +Y=손가락, +Z=손등 컨벤션에 맞추는 회전. RIGHT_HAND_REST_HPR
# (그립 잡은 자세) 과는 다른 레이어 — 그건 손목 pivot 의 최종 자세, 이건 모델 mesh 의
# intrinsic 방향 보정.
#
# DJMaesen FPS Arms 는 양손 통합 mesh + 라이브 스켈레톤. setH(180) 으로 손가락이
# pistol +Y(전방) 으로 향함 (X 도 같이 뒤집혀 split L/R 라벨은 _load_external 에서 스왑).
# P=-15 로 어깨가 약간 아래로 기울어 cross-section 이 화면 밖. R 은 본 단위 제어
# 가 가능해질 때까지 0 또는 작은 값 (큰 roll 은 전체 팔이 휘둘림).
#
# 본 모델은 size 56 × 60 × 21 raw units 라 SCALE 0.014 가 적절 (~0.84m). 스펙의
# 0.10 은 다른 모델 가정 — 이 모델엔 너무 큼.
MODEL_SCALE = 0.014
MODEL_HPR_RIGHT = (180, -15, -10)
MODEL_HPR_LEFT = (180, -15, 90)
# Mesh split 패턴이라 좌/우 POS 따로 — setSx(-1) 미러는 양손 통합 mesh 한쪽에만
# 적용 못해서 사용 안 함. POS 의 X 부호로 각 팔의 안쪽 모서리(손목) 가 self.np 원점에
# 오도록 좌/우 따로 보정.
MODEL_POS_RIGHT = Vec3(-0.077, -0.62, 0)
MODEL_POS_LEFT = Vec3(+0.077, -0.62, 0)


def _split_dual_arm_geom():
    """DJMaesen scene.gltf 를 한 번만 로드해 단일 GeomNode 를 좌/우 두 GeomNode 로 분리.

    원본 정점은 그대로 두고 primitives (삼각형) 만 centroid X 부호에 따라 두 그룹으로
    나눠 각각 새 Geom 으로 묶는다. 같은 GeomVertexData 를 공유하므로 메모리 비용 작음.

    반환: { "left": GeomNode wrapped NodePath, "right": GeomNode wrapped NodePath }.

    skinning bone influence 와 무관하게 rest-pose 정점 좌표로 split — 이 모델은
    rest pose 에서 좌/우 팔이 X=0 평면 좌우로 깨끗하게 분리돼 있어 정확.
    """
    if _SPLIT_GEOMS:
        return _SPLIT_GEOMS

    root = NodePath(gltf.load_model(_ARM_GLB_PATH))
    geom_nps = root.findAllMatches("**/+GeomNode")
    if len(geom_nps) != 1:
        raise RuntimeError(
            f"expected exactly 1 GeomNode in arm model, found {len(geom_nps)}"
        )
    geom_node = geom_nps[0].node()
    orig_geom = geom_node.getGeom(0)
    orig_state = geom_node.getGeomState(0)
    vdata = orig_geom.getVertexData()

    # 정점 위치 미리 캐싱 (반복 조회 비용 절감).
    vreader = GeomVertexReader(vdata, "vertex")
    positions: list = []
    while not vreader.isAtEnd():
        positions.append(vreader.getData3())

    # 모든 primitives 를 삼각형으로 decompose 후 centroid X 부호로 분류.
    left_tris: list = []
    right_tris: list = []
    for prim_idx in range(orig_geom.getNumPrimitives()):
        prim = orig_geom.getPrimitive(prim_idx).decompose()
        nverts_per_prim = 3  # decompose 후 모두 triangle
        for t in range(prim.getNumPrimitives()):
            i0 = prim.getVertex(t * nverts_per_prim + 0)
            i1 = prim.getVertex(t * nverts_per_prim + 1)
            i2 = prim.getVertex(t * nverts_per_prim + 2)
            cx = (positions[i0].x + positions[i1].x + positions[i2].x) / 3.0
            (left_tris if cx < 0 else right_tris).append((i0, i1, i2))

    def _make_geom_node(name: str, tris: list) -> NodePath:
        gtris = GeomTriangles(Geom.UHStatic)
        for i0, i1, i2 in tris:
            gtris.addVertices(i0, i1, i2)
            gtris.closePrimitive()
        new_geom = Geom(vdata)
        new_geom.addPrimitive(gtris)
        gn = GeomNode(name)
        gn.addGeom(new_geom, orig_state)
        return NodePath(gn)

    _SPLIT_GEOMS["left"] = _make_geom_node("arm_left_split", left_tris)
    _SPLIT_GEOMS["right"] = _make_geom_node("arm_right_split", right_tris)
    print(
        f"[hands] arm mesh split — left tris: {len(left_tris)}, right tris: {len(right_tris)}",
        flush=True,
    )
    return _SPLIT_GEOMS


class Hand:
    def __init__(self, name, parent_np, base):
        self.base = base
        self.name = name
        self.np = parent_np.attachNewNode(f"hand_{name}_root")
        # 손은 pistol.np 자식이라 main.py 에서 부착한 weapon_key/fill 라이트가 자동 상속.
        # setLightOff 는 안 함 (PBR 음영 살리려면 라이트 필요).
        # ADS 진입/해제 시 LerpColorScaleInterval 로 알파를 0↔1 페이드.
        self.np.setTransparency(TransparencyAttrib.MAlpha)

        loaded = False
        use_external = USE_EXTERNAL_MODEL and os.path.exists(_ARM_GLB_PATH)
        if use_external:
            try:
                self._load_external()
                loaded = True
            except Exception as e:  # noqa: BLE001
                print(
                    f"[hands] external arm load failed — fallback to box: {e}",
                    flush=True,
                )
                for child in list(self.np.getChildren()):
                    child.removeNode()

        if not loaded:
            # 박스 폴백: 텍스처 stage off 후 박스 조립.
            self.np.setTextureOff(1)
            self._build_box_fallback()

    def _load_external(self):
        """DJMaesen FPS Arms 모델을 정점 X 부호 기반으로 split → 좌/우 GeomNode 중 하나만
        해당 Hand 인스턴스에 attach. 같은 GeomVertexData (정점/skin) 공유라 메모리 효율적.

        설계:
          - _split_dual_arm_geom() 가 첫 호출 시 mesh 를 한 번만 split 해 모듈 캐시.
          - "right" 인스턴스 → right_arm GeomNode instance, "left" 인스턴스 → left_arm.
          - 각 instanceTo 로 같은 GeomNode 를 여러 위치에 부착 (메모리 1 회).
          - 미러(setSx -1) 안 함 — split 자체가 좌/우 자연 분리라 미러 불필요.
        """
        splits = _split_dual_arm_geom()
        # setH(180) 이 X 도 뒤집어 right_arm GeomNode (vertex X>0) 가 회전 후 화면 왼쪽으로
        # 가서 split 라벨을 의도적 스왑. 본 모델 fingers/wrist 가 +Y 가 아닌 다른 축이면
        # MODEL_HPR_* 의 H 를 조정.
        side = "left" if self.name == "right" else "right"
        arm = self.np.attachNewNode("arm_split_attach")
        splits[side].instanceTo(arm)
        arm.setScale(MODEL_SCALE)
        hpr = MODEL_HPR_RIGHT if self.name == "right" else MODEL_HPR_LEFT
        arm.setHpr(*hpr)
        pos = MODEL_POS_RIGHT if self.name == "right" else MODEL_POS_LEFT
        arm.setPos(pos)

        # 디버그: 오른쪽 인스턴스 한 번만 노드 트리 + bbox 출력. 본 이름 (R_arm_025 등)
        # 확인용 — 향후 본 단위 제어 시 정확한 이름 필요.
        if self.name == "right":
            print("[hands] model node tree:", flush=True)
            arm.ls()
            bb_min, bb_max = arm.getTightBounds()
            print(
                f"[hands] arm bbox(np-local): {bb_min} ~ {bb_max}  size: {bb_max - bb_min}",
                flush=True,
            )

        # 박스 폴백과의 인터페이스 일관성용 핸들 (외부 코드 참조 없음).
        self.fist = arm
        self.forearm = arm
        self.sleeve = arm

        # 첫 실행 진단.
        bb_min, bb_max = arm.getTightBounds(self.np)
        print(
            f"[hands] {self.name} arm loaded (split mesh). bounds(np-local) = "
            f"{bb_min} .. {bb_max}  size = {bb_max - bb_min}",
            flush=True,
        )

    def _build_box_fallback(self):
        """기존 박스 손 — 외부 모델 로드 실패 / USE_EXTERNAL_MODEL=False 일 때."""
        # 주먹 — hand_root 원점 부근에 센터
        self.fist = self.base.loader.loadModel("models/box")
        self.fist.reparentTo(self.np)
        self.fist.setScale(0.065, 0.08, 0.065)
        self.fist.setPos(-0.0325, -0.04, -0.0325)
        self.fist.setMaterial(_SKIN_MAT)

        # 팔뚝 — 손목 뒤(-Y) 방향으로 0.45m
        self.forearm = self.base.loader.loadModel("models/box")
        self.forearm.reparentTo(self.np)
        self.forearm.setScale(0.05, 0.45, 0.05)
        self.forearm.setPos(-0.025, -0.45, -0.025)
        self.forearm.setMaterial(_SKIN_MAT)

        # 소매 — forearm 뒤쪽에 더 진한 색 박스
        self.sleeve = self.base.loader.loadModel("models/box")
        self.sleeve.reparentTo(self.np)
        self.sleeve.setScale(0.055, 0.15, 0.055)
        self.sleeve.setPos(-0.0275, -0.525, -0.0275)
        self.sleeve.setMaterial(_SLEEVE_MAT)
