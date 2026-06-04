"""무기/보이는 몸 배치 튜닝 상수 — zombie_game.py 에서 import.

게임 중 튜닝(B=총↔몸 모드, 화살표/PgUp·Dn=위치, [ ] ; ' , .=회전, M=총구 마커,
P=값 출력)으로 찾은 값을 여기에 박아둔다. 동작 로직은 zombie_game.py 에 있고,
이 파일은 숫자값만 모아 둔 설정 파일 — 필요할 때 꺼내 쓰거나 다른 빌드에 재사용.

좌표계
  *_LOCAL_POS / HPR : weapon_anchor(= 오른손 본의 world pos+hpr 따라감) 로컬, m.
  *_MUZZLE_POS      : weapon_anchor 로컬, m. +Y 가 총신 전방. muzzle flash/tracer 시작점.
  *_LOCAL_SCALE     : 모델 native 크기 정규화 배율.
  *_LOCAL_PREROT    : 모델 native 방향 보정 (배치 HPR 과 분리).
  WEAPON_BODY_*     : 무기별 "보이는 몸(ybot)" 평행이동/회전. player-frame, m/deg.
                      카메라·히트박스 불변. 몸+총이 같은 축으로 함께 회전.
"""

# ── 권총 (9mm) ──────────────────────────────────────────────────────────────
WEAPON_LOCAL_SCALE = 0.1195
WEAPON_LOCAL_POS   = (0.000, 0.090, 0.040)
WEAPON_LOCAL_HPR   = (22.5, -78.2, 108.9)
WEAPON_MUZZLE_POS  = (0.08, 0.32, 0.08)

# ── 소총 (AR-10) ────────────────────────────────────────────────────────────
RIFLE_LOCAL_SCALE  = 0.0810
RIFLE_LOCAL_POS    = (0.024, 0.280, 0.030)
RIFLE_LOCAL_HPR    = (27.5, -104.2, 93.9)
RIFLE_MUZZLE_POS   = (-0.170, 0.750, -0.090)
RIFLE_LOCAL_PREROT = (180, 0, 0)   # 모델이 권총과 앞뒤 반대 → up(Z)축 180° 보정

# ── 무기별 "보이는 몸" 오프셋 / 회전 ─────────────────────────────────────────
WEAPON_BODY_OFFSET = {
    'pistol': (0.0, 0.0, 0.0),
    'rifle':  (-0.110, -0.020, 0.110),
}
WEAPON_BODY_HPR = {
    'pistol': (0.0, 0.0, 0.0),
    'rifle':  (-2.0, 0.0, 0.0),
}

# 무기별 ADS(줌, 우클릭) 시 보이는 몸 이동 오프셋 (우, 앞, 위 / m). aim_t 로 ramp.
# 카메라는 같은 양 역보정 → 시점 정적. 줌 시 총이 화면 중앙에 오도록 조정.
# 소총은 평소 몸 오프셋(WEAPON_BODY_OFFSET)이 왼쪽으로 치우쳐 있어, 권총과 동일한
# ADS 값을 쓰면 총이 더 왼쪽으로 빠져 안 보임 → 소총 전용 값으로 중앙 정렬.
WEAPON_ADS_OFFSET = {
    'pistol': (-0.13, 0.05, -0.02),
    'rifle':  (-0.030, 0.205, 0.055),
}

# 사격 탄 퍼짐(발로란트식) — 각도 deg. 연사할수록 _spray_shots 증가(첫발은 정확),
# reset 초 동안 안 쏘면 0 으로 리셋.
#  mode 'pattern'(소총): 약한 상승 중심(v_step*발수, v_max 캡) 둘레로 사방 랜덤 콘.
#      콘 반경은 cone_min→cone_max 로 cone_ramp 발에 걸쳐 커짐 → 연사할수록 사방으로
#      더 크게 튐(한 방향 쏠림 X).
#  mode 'scatter'(권총): 빨리 연타할수록 랜덤 콘 반경(step*발수, max_shots 캡) 증가.
#  'move': 이동(WASD) 중이면 매 발 추가되는 랜덤 콘 반경(deg) — 가만히 있을 때보다
#          크게 퍼짐(발로란트식 이동 부정확). 연사 발수와 무관, 첫발부터 적용.
#  'ads' : 조준(우클릭 줌) 시 퍼짐 배율. 줌하면 전체 퍼짐에 이 값을 곱함(작을수록
#          정밀). 줌 정도(aim_t)에 따라 1.0 ↔ ads 로 보간.
WEAPON_SPRAY = {
    'pistol': {'mode': 'scatter', 'step': 0.95, 'max_shots': 8, 'reset': 0.22,
               'move': 2.4, 'ads': 0.40},
    'rifle':  {'mode': 'pattern', 'v_step': 0.55, 'v_max': 10,
               'cone_min': 0.0, 'cone_max': 8.5, 'cone_ramp': 6,
               'max_shots': 24, 'reset': 0.18, 'move': 4.0, 'ads': 0.35},
}
