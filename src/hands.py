"""1인칭 손 모델 — fist + forearm + sleeve 박스 조립.

Doom/Wolfenstein 스타일 1인칭 구도용으로 팔뚝이 길게 카메라 쪽으로
뻗어 들어오도록 forearm 길이를 키우고, 뒤쪽 끝에 진한 색 소매를 붙임.

hand_root (NodePath) 원점 = 손목 위치.
  ├── fist     — 주먹. 원점 부근에 센터.
  ├── forearm  — 팔뚝. 손목 뒤(-Y)로 약 0.45m 뻗음.
  └── sleeve   — 팔뚝 뒤끝의 옷소매(어두운 색).

좌표 컨벤션: 부품 setPos는 corner-origin unit cube 기준이라
"센터 위치"가 필요하면 scale의 절반을 빼서 setPos를 계산한다.

사용 예:
    hand = Hand("right", parent_np=pistol_root, base=base)
    hand.np.setPos(...)
    hand.np.setHpr(...)
"""

from panda3d.core import TransparencyAttrib, Vec4


HAND_COLOR = Vec4(0.75, 0.55, 0.45, 1)
SLEEVE_COLOR = Vec4(0.25, 0.30, 0.32, 1)


class Hand:
    def __init__(self, name, parent_np, base):
        self.base = base
        self.np = parent_np.attachNewNode(f"hand_{name}_root")
        # 카메라 회전에 따라 directional light가 손을 어둡게 만드는 걸 막기 위해
        # 권총과 동일하게 라이팅을 끔. 자식들도 자동 상속.
        self.np.setLightOff()
        # ADS 진입/해제 시 LerpColorScaleInterval 로 알파를 0↔1 페이드.
        # 자식 setColor 의 alpha 와 colorScale alpha 가 곱해지므로 모두 영향.
        self.np.setTransparency(TransparencyAttrib.MAlpha)

        # 주먹 — hand_root 원점 부근에 센터
        # scale 0.065 × 0.08 × 0.065 → 코너 origin이라 setPos를 절반씩 빼서 센터에 둠
        self.fist = base.loader.loadModel("models/box")
        self.fist.reparentTo(self.np)
        self.fist.setScale(0.065, 0.08, 0.065)
        self.fist.setPos(-0.0325, -0.04, -0.0325)
        self.fist.setColor(HAND_COLOR)

        # 팔뚝 — 손목 뒤(-Y) 방향으로 0.45m. 팔 단면이 화면에서 안 보이도록 길게.
        # 센터 (0, -0.225, 0) → corner-origin setPos.y = -0.225 - 0.225 = -0.45.
        self.forearm = base.loader.loadModel("models/box")
        self.forearm.reparentTo(self.np)
        self.forearm.setScale(0.05, 0.45, 0.05)
        self.forearm.setPos(-0.025, -0.45, -0.025)
        self.forearm.setColor(HAND_COLOR)

        # 소매 — forearm 뒤쪽에 더 진한 색 박스 (옷소매처럼).
        # 센터 (0, -0.45, 0) → corner-origin setPos.y = -0.45 - 0.075 = -0.525.
        self.sleeve = base.loader.loadModel("models/box")
        self.sleeve.reparentTo(self.np)
        self.sleeve.setScale(0.055, 0.15, 0.055)
        self.sleeve.setPos(-0.0275, -0.525, -0.0275)
        self.sleeve.setColor(SLEEVE_COLOR)
        self.sleeve.setLightOff()
