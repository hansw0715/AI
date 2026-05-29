"""
zombie_game — Mirror's Edge style 1인칭 좀비 슈터 (Panda3D)
Stage 1: 1인칭 카메라 + Y Bot 풀바디 + 기본 입력.
"""
import random
from math import cos, radians, sin
from pathlib import Path

from direct.actor.Actor import Actor
from direct.gui.DirectGui import DirectButton, DirectFrame
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from panda3d.core import (
    AmbientLight, CardMaker, ClockObject, DirectionalLight, Filename,
    LineSegs, NodePath, Quat, TextNode, Vec3, Vec4, WindowProperties,
)


SCRIPT_DIR = Path(__file__).parent
BAM_PATH = Filename.from_os_specific(
    str(SCRIPT_DIR / 'assets' / 'ybot' / 'scene.bam')
)
WEAPON_PATH = Filename.from_os_specific(
    str(SCRIPT_DIR / 'assets' / 'weapons' / '9mm_pistol.bam')
)

# 권총 attach knob.
#   WEAPON_WORLD_SIZE : 권총의 world 기준 절대 길이 (m). 모델 size 2.21m 가 이
#                       값으로 normalize. Mixamo hand 본의 cm 단위 스케일 잔재를
#                       무시하려 setScale(self.render, ...) 사용.
#   WEAPON_LOCAL_POS  : hand 본 좌표계 기준 권총 위치. hand 본 자체가 cm 단위라
#                       작은 값이 큰 효과 — 0.01 이면 1cm 정도.
#   WEAPON_LOCAL_HPR  : hand 본 좌표계 기준 회전 (H,P,R degree).
# F2 디버그 카메라로 보면서 미세조정.
# weapon_anchor (hand 본의 world pos+hpr 따라감) 기준 weapon local transform.
# HPR 는 weapon 의 self frame 기준 누적 회전 끝 자세 → 그대로 setHpr 호출 가능.
WEAPON_LOCAL_SCALE = 0.1195
WEAPON_LOCAL_POS   = (0.000, 0.090, 0.040)
WEAPON_LOCAL_HPR   = (22.5, -78.2, 108.9)


class ZombieGame(ShowBase):
    def __init__(self):
        super().__init__()

        # 윈도우/마우스
        props = WindowProperties()
        props.setTitle('zombie_game')
        props.setCursorHidden(True)
        props.setMouseMode(WindowProperties.M_confined)
        self.win.requestProperties(props)
        self.disableMouse()  # ShowBase 기본 마우스-카메라 비활성

        # 환경
        self.setBackgroundColor(0.45, 0.6, 0.85)
        self._make_lights()
        self._make_ground()
        self._make_landmarks()

        # 카메라 — 캐릭터 머리 안쪽에서 보더라도 클리핑 안 되게 near 매우 작게.
        # FOV 크면 시야 넓어지고 자기 몸이 작게 보임 (FPS 표준 90~100).
        self.camLens.setNear(0.01)
        self.camLens.setFov(100)

        # 플레이어 상태 (panda3d 표준: Z-up, Y-forward)
        self.player_pos = Vec3(0, 0, 0)  # 발 기준
        self.player_yaw = 0.0            # H (좌우)
        self.player_pitch = 0.0          # P (위아래)
        self.player_vz = 0.0
        self.on_ground = True
        self.head_height = 1.65
        self.move_speed = 6.0
        self.mouse_sens = 0.15
        self.jump_speed = 4.5
        self.gravity = 12.0

        # Y Bot Actor (월드에 직접 부착)
        self.ybot = Actor(BAM_PATH)
        self.ybot.reparentTo(self.render)
        self.ybot.setPos(self.player_pos)
        # Mixamo Y Bot은 보통 panda -Y를 봄. 캐릭터 forward를 +Y(player_yaw=0 시
        # 카메라가 보는 방향)에 맞추려면 H 에 180을 더해야 함.
        self.ybot.setH(self.player_yaw + 180)
        self.anim_names = list(self.ybot.getAnimNames())
        print(f'[zombie_game] animations: {self.anim_names}', flush=True)

        # 골격을 3파트로 분리.
        #   lower : Hips + 다리/발            → 항상 locomotion (펀치 모드에서도 다리는 안 멈춤)
        #   upper : Spine + 자손 (손 제외)   → locomotion
        #   hands : 양손 + 손가락             → Shoot 단발 또는 upper 와 동기화
        # 글로브 패턴 주의: '*' 는 빈 문자열 포함이라 'Spine' 만 정확히 매치하고
        # 'Spine1' 은 매치 안 함 → upper 의 include='*Spine' 으로 Spine 본 하나만
        # 잡고 자손은 hierarchy 로 자동 포함. lower 의 exclude='*Spine*' 은 양옆
        # 와일드카드라 Spine/Spine1/Spine2 모두 잡아 자손까지 lower 에서 제외.
        # 그리고 Actor 내부 traversal 이 `if include / elif exclude` 순서라 include
        # 패턴이 너무 광범위하면 exclude 가 무시되므로 include 는 좁게 잡는 게 안전.
        self._parts = ('lower', 'upper', 'hands')
        self.ybot.makeSubpart(
            'lower',
            includeJoints=['*Hips'],
            excludeJoints=['*Spine*', '*LeftHand*', '*RightHand*'],
        )
        self.ybot.makeSubpart(
            'upper',
            includeJoints=['*Spine'],
            excludeJoints=['*LeftHand*', '*RightHand*'],
        )
        self.ybot.makeSubpart(
            'hands',
            includeJoints=['*LeftHand*', '*RightHand*'],
        )

        # 블렌딩 모드: 여러 애니메이션을 동시에 돌리면서 weight 로 섞는다.
        # Unity 의 crossfade 와 동일한 효과 — 액션 전환 시 움찔거림 제거.
        self.ybot.enableBlend()
        if 'Idle' in self.anim_names:
            for p in self._parts:
                self.ybot.loop('Idle', partName=p)

        # Kneel 상태 머신: stand → (going_down=StandToKneel 단발) → kneel
        #                 kneel → (going_up=KneelToStand 단발) → stand
        # transition 중에는 이동/사격 모두 잠금.
        self.kneel_state = 'stand'
        self.current_anim = 'Idle'        # upper 파트의 현재 상태 (HUD 표시용)
        self._hands_oneshot = False       # hands 가 Shoot 단발 중인지
        self._anim_token = 0              # Kneel transition 단발 토큰
        self._hands_token = 0             # Shoot 단발 토큰
        self._reload_oneshot = False
        self._reload_token = 0
        # 각 파트·애니메이션의 현재 weight, 목표 weight. _update_blend 가 매 프레임
        # 지수 평활로 current → target 수렴시킨다.
        self._current_w = {
            p: {a: (1.0 if a == 'Idle' else 0.0) for a in self.anim_names}
            for p in self._parts
        }
        self._target_w = {p: dict(d) for p, d in self._current_w.items()}
        for p in self._parts:
            for a, w in self._current_w[p].items():
                self.ybot.setControlEffect(a, w, partName=p)
        self.blend_speed = 14.0       # 크면 빠른 전환, 작으면 부드러움
        self.blend_out_time = 0.18    # 단발 anim 끝나기 이만큼 전부터 다음 상태로 페이드

        # 모든 locomotion anim 을 양쪽 파트에서 항상 loop — weight 가 0 이어도
        # 내부 time 은 흐르고, 보이는 건 _current_w 가 결정. 액션 전환 시 시작
        # 프레임이 갑자기 튀지 않게 함.
        self._loop_anim_set = {
            'Idle', 'RunForward', 'RunBackward', 'StrafeL', 'StrafeR',
            'KneelIdle', 'Jump',
            # Walk* 도 loop 만 깔아둠 — 현재 코드에선 미사용이지만 추후 Shift+이동
            # 같은 걸 붙일 때 시작 프레임이 튀지 않게 미리 돌려 둠.
            'WalkForward', 'WalkBackward',
        }
        for a in self.anim_names:
            if a in self._loop_anim_set:
                for p in self._parts:
                    self.ybot.loop(a, partName=p)

        # 사격 반동 — 카메라가 아닌 weapon_anchor 에 적용해서 권총+팔이 살짝
        # 뒤로 빠지는 효과. recoil_back 만 사용, pitch 킥은 거슬려서 제거.
        self.recoil_back = 0.0           # 현재 반동 양 (m, world 단위)
        self.recoil_decay = 10.0         # 1/sec, 클수록 빨리 복귀
        self.recoil_shoot_back = 0.03    # 발사 시 인가되는 뒤로 오프셋 (3cm — pistol 적당)

        # Reload 중 W/S 걸을 때 lower 가 Idle 로 고정되어 몸이 미끄러지는 느낌
        # → ybot 에 사인파 Z bob 을 더하고 카메라엔 같은 값을 빼서 상쇄. 화면은
        # 정적, 자기 팔·손·총만 위아래로 까딱이는 효과. _walk_bob_t 로 reload+이동
        # 조건일 때만 ramp in, 끝나면 ramp out.
        self._walk_bob_t = 0.0
        self._walk_bob_phase = 0.0
        self._walk_bob_amp_z = 0.025     # peak ±2.5cm
        self._walk_bob_freq = 10.0       # rad/s (≈ 1.6 Hz)
        self._walk_bob_speed = 5.0       # in/out ramp 1/sec

        # Hips root motion 상쇄용. Mixamo 머지 .bam 은 각 액션의 Hips 시작 위치가
        # 미묘하게 달라서 (예: Idle Y=-0.944, Shoot Y=-0.892) 액션 전환 시 캐릭터
        # 전체가 5cm 가량 카메라 방향으로 평행이동 → 머리가 카메라 안으로 밀려들어와
        # 뒤통수가 화면을 덮음. 매 프레임 Hips 의 actor-local XY drift 를 측정해서
        # actor NodePath 를 반대로 밀어줘서 시각적 anchor 를 고정한다. Z(높이) 는
        # 그대로 둬서 anim 의 자연스러운 body bob 은 유지.
        hips_name = next(
            (j.getName() for j in self.ybot.getJoints() if j.getName().endswith('Hips')),
            None,
        )
        head_name = next(
            (j.getName() for j in self.ybot.getJoints() if j.getName().endswith('Head')),
            None,
        )
        print(f'[zombie_game] hips/head joints: {hips_name} / {head_name}', flush=True)
        # makeSubpart 이후 'modelRoot' 는 어느 subpart 에도 속하지 않은 본만 다루므로
        # exposeJoint 는 본이 실제로 속한 subpart 이름으로 호출해야 함. 카메라가
        # head 본을 따라가야 하므로 매 프레임 위치가 필요. Hips=lower, Head=upper.
        self.hips_joint = (
            self.ybot.exposeJoint(None, 'lower', hips_name) if hips_name else None
        )
        self.head_joint = (
            self.ybot.exposeJoint(None, 'upper', head_name) if head_name else None
        )
        self._hips_ref_local = None

        # 권총 메쉬: RightHand 본에 attach — 본 transform 따라 손에 붙어 다님.
        rhand_name = next(
            (j.getName() for j in self.ybot.getJoints() if j.getName().endswith('RightHand')),
            None,
        )
        self.right_hand_joint = (
            self.ybot.exposeJoint(None, 'hands', rhand_name) if rhand_name else None
        )
        if self.right_hand_joint is not None and WEAPON_PATH.exists():
            self.weapon = self.loader.loadModel(WEAPON_PATH)
            # glTF RootNode self-transform 우회용 평탄화 (slide/trigger 보존).
            self.weapon.flattenLight()
            # weapon anchor — hand 본의 위치만 매 프레임 복사하고 회전은 무시한다.
            # 이렇게 하면 weapon 의 H/P/R 축이 world 축과 정렬되어 직관적으로 회전
            # 가능 (hand 본의 자체 회전이 weapon 의 회전축을 비틀어서 H 와 R 이
            # 같은 효과를 내는 문제 해결). 단점: 손 자세 변해도 weapon 자세는
            # 고정 — base orientation 잡는 단계엔 오히려 편함. 자세 다 잡힌 후
            # hand 본 회전도 같이 따라가게 하려면 anchor 의 setHpr 도 매 프레임
            # hand 회전으로 갱신하면 됨.
            self.weapon_anchor = self.render.attachNewNode('weapon_anchor')
            self.weapon.reparentTo(self.weapon_anchor)
            self.weapon.setScale(WEAPON_LOCAL_SCALE)
            self.weapon.setPos(*WEAPON_LOCAL_POS)
            self.weapon.setHpr(*WEAPON_LOCAL_HPR)
            self.weapon.setTwoSided(True)
            # anchor 갱신은 _update 안에서 ybot.update(force=True) 직후에 호출 —
            # 별도 task 로 두면 frame order 가 어긋나서 1프레임 lag (잔상) 발생.
            print(f'[zombie_game] weapon attached to {rhand_name}', flush=True)

            # Slide 노드 (사격 시 후퇴 효과용). flattenLight 가 named node 는
            # 보존하므로 find 로 찾을 수 있음. 모델의 총신 축이 X 라서 -X 방향 후퇴.
            self.slide_node = self.weapon.find('**/Slide')
            if self.slide_node.isEmpty():
                self.slide_node = None
                print('[weapon] Slide node not found', flush=True)
            else:
                self.slide_rest_x = self.slide_node.getX()
                print(f'[weapon] Slide found, rest X = {self.slide_rest_x:.3f}',
                      flush=True)
            # 슬라이드 후퇴 상태
            self.slide_recoil = 0.0
            self.slide_recoil_kick = 0.4   # 모델 local units (음수 X 로 후퇴)
            self.slide_recoil_decay = 14.0 # 1/sec — 클수록 빠른 복귀

        else:
            self.weapon = None
            print(f'[zombie_game] WARN weapon not loaded '
                  f'(rhand={rhand_name}, glb_exists={WEAPON_PATH.exists()})',
                  flush=True)

        # 슬라이드 위치 marker (RightHand 본 좌표계 — armature cm 단위) — 임시 하네스
        if self.right_hand_joint is not None and not self.right_hand_joint.isEmpty():
            ls = LineSegs()
            ls.setThickness(3)
            size = 5.0  # 5cm 축 길이
            for color, axis in (
                ((1, 0, 0, 1), Vec3(size, 0, 0)),   # X 빨강
                ((0, 1, 0, 1), Vec3(0, size, 0)),   # Y 초록 (총신 방향 추정)
                ((0, 0, 1, 1), Vec3(0, 0, size)),   # Z 파랑 (위 추정)
            ):
                ls.setColor(*color)
                ls.moveTo(0, 0, 0)
                ls.drawTo(axis)
            self.slide_marker = self.right_hand_joint.attachNewNode(ls.create())
            self.slide_marker.setLightOff()
            self._marker_pos = [0.0, 0.0, 0.0]
            self.slide_marker.setPos(0, 0, 0)
            print('[marker] axes: red=X green=Y blue=Z. I/K=±Y, J/L=±X, U/O=±Z, P=dump',
                  flush=True)
        else:
            self.slide_marker = None
        # 카메라를 Head 본의 월드 좌표에 매 프레임 따라붙임. 머리가 애니메이션으로
        # 흔들려도 카메라가 동행하니까 자기 뒤통수가 보이는 일이 없음.
        # 시선 방향(yaw/pitch) 은 마우스 입력 그대로 — head 본의 회전은 무시.
        self.eye_forward_offset = 0.18  # 머리 본 중심에서 시선 방향으로 m
        self.eye_lateral_offset = 0.10  # 카메라를 왼쪽으로 (m) → 권총 우측 배치

        # 입력
        self.keys = {'w': False, 'a': False, 's': False, 'd': False, 'space': False}
        # editor 모드: F2 로 토글하는 free-cam. 진입 시 현재 카메라 위치/방향에서
        # 시작하고 마우스 룩 + WASD/Space 로 자유 비행.
        self.editor_mode = False
        self.editor_pos = Vec3(0, -5, 1.6)
        self.editor_yaw = 0.0
        self.editor_pitch = 0.0
        self.editor_speed = 8.0
        self._bind_inputs()

        # 마우스 센터링
        self._win_cx = self.win.getXSize() // 2
        self._win_cy = self.win.getYSize() // 2
        self.win.movePointer(0, self._win_cx, self._win_cy)
        self._first_frame = True

        # HUD
        self.hud = OnscreenText(
            text='',
            pos=(-1.7, 0.92), scale=0.045,
            fg=(1, 1, 1, 1), bg=(0, 0, 0, 0.5),
            align=TextNode.ALeft, mayChange=True,
            parent=self.aspect2d,
        )

        # 일시정지 메뉴 (ESC 토글)
        self.paused = False
        self._build_pause_menu()

        # 메인 루프
        self.taskMgr.add(self._update, 'game_update')

        # 진단: Idle 한 프레임 돌고 나서 본 이름/좌표 한 번 출력
        self.taskMgr.doMethodLater(0.3, self._dump_joints, 'dump_joints')

    # --- world setup --------------------------------------------------------

    def _make_lights(self):
        amb = AmbientLight('ambient')
        amb.setColor(Vec4(0.4, 0.4, 0.4, 1))
        self.render.setLight(self.render.attachNewNode(amb))

        dl = DirectionalLight('dir')
        dl.setColor(Vec4(0.85, 0.85, 0.8, 1))
        dlnp = self.render.attachNewNode(dl)
        dlnp.setHpr(45, -55, 0)
        self.render.setLight(dlnp)

    def _make_ground(self):
        cm = CardMaker('ground')
        cm.setFrame(-32, 32, -32, 32)
        gnd = self.render.attachNewNode(cm.generate())
        gnd.setHpr(0, -90, 0)  # XY 평면으로 눕히기
        gnd.setColor(0.55, 0.55, 0.58, 1)

    def _make_landmarks(self):
        # 빈 월드면 이동 감각이 없으니 색깔 막대 몇 개를 흩뿌려서 시각적 단서.
        rng = random.Random(42)
        for i in range(10):
            cm = CardMaker(f'mark_{i}')
            cm.setFrame(-0.4, 0.4, 0, 2.0)
            card = self.render.attachNewNode(cm.generate())
            card.setTwoSided(True)
            card.setPos(rng.uniform(-15, 15), rng.uniform(-15, 15), 0)
            card.setH(rng.uniform(0, 360))
            card.setColor(rng.uniform(0.3, 1), rng.uniform(0.3, 1), rng.uniform(0.3, 1), 1)

    # --- input --------------------------------------------------------------

    def _bind_inputs(self):
        for k in ('w', 'a', 's', 'd', 'space'):
            self.accept(k, self._set_key, [k, True])
            self.accept(f'{k}-up', self._set_key, [k, False])
        self.accept('escape', self._toggle_pause)
        self.accept('mouse1', self._play_shoot_oneshot)
        self.accept('r', self._play_reload_oneshot)
        self.accept('f2', self._toggle_editor)
        # Ctrl 토글 — Panda3D 에선 'control' 단독 이벤트가 안 들어오므로 lcontrol/
        # rcontrol 만 바인딩 (left/right 둘 다 잡힘)
        for k in ('lcontrol', 'rcontrol'):
            self.accept(k, self._toggle_kneel)
        # 슬라이드 위치 marker 튜닝 키 (임시 하네스)
        step = 2.0  # 2cm armature unit
        marker_binds = {
            'i': (1, step),  'k': (1, -step),   # ±Y (총신 방향)
            'j': (0, -step), 'l': (0, step),    # ±X (좌우)
            'u': (2, step),  'o': (2, -step),   # ±Z (위아래)
        }
        for key, args in marker_binds.items():
            self.accept(key, self._nudge_marker, list(args))
            self.accept(f'{key}-repeat', self._nudge_marker, list(args))
        self.accept('p', self._dump_marker)

    def _set_key(self, k, v):
        self.keys[k] = v

    # --- slide marker tuning harness (조정 끝나면 제거) -----------------------

    def _nudge_marker(self, idx, delta):
        if self.slide_marker is None:
            return
        self._marker_pos[idx] += delta
        self.slide_marker.setPos(*self._marker_pos)

    def _dump_marker(self):
        if self.slide_marker is None:
            return
        p = self._marker_pos
        print(f'[marker] RightHand-local X={p[0]:.2f} Y={p[1]:.2f} Z={p[2]:.2f}',
              flush=True)
        # 화면 가운데 큰 글씨로 3초 — 이전 표시 있으면 교체
        txt = (f'MARKER (RightHand-local)\n'
               f'SLIDE_RIGHT = {p[0]:.2f}\n'
               f'SLIDE_FWD   = {p[1]:.2f}\n'
               f'SLIDE_UP    = {p[2]:.2f}')
        if hasattr(self, '_marker_text') and self._marker_text is not None:
            self._marker_text.destroy()
        self._marker_text = OnscreenText(
            text=txt, pos=(0, 0.2), scale=0.07,
            fg=(1, 1, 0, 1), bg=(0, 0, 0, 0.85),
            align=TextNode.ACenter, mayChange=False,
            parent=self.aspect2d,
        )
        token = self._marker_text
        def _remove(task, t=token):
            if self._marker_text is t:
                self._marker_text.destroy()
                self._marker_text = None
            return Task.done
        self.taskMgr.doMethodLater(3.0, _remove, 'marker_dump_remove')

    # --- weapon tuning harness (조정 끝나면 통째로 제거) -------------------


    def _toggle_kneel(self):
        if self._reload_oneshot:
            return
        # transition 중에는 무시 (anim 끝까지 재생).
        if self.kneel_state in ('going_down', 'going_up'):
            return
        if self.kneel_state == 'stand':
            if 'StandToKneel' in self.anim_names:
                self._play_kneel_transition('StandToKneel', 'going_down', 'kneel')
            elif 'KneelIdle' in self.anim_names:
                self.kneel_state = 'kneel'  # transition anim 없으면 즉시 전환
        else:  # 'kneel'
            if 'KneelToStand' in self.anim_names:
                self._play_kneel_transition('KneelToStand', 'going_up', 'stand')
            else:
                self.kneel_state = 'stand'

    def _play_kneel_transition(self, anim_name, mid_state, end_state):
        """무릎꿇기/일어서기 transition 단발 — 모든 파트에 anim 적용."""
        self.kneel_state = mid_state
        self.current_anim = anim_name
        new_t = {a: (1.0 if a == anim_name else 0.0) for a in self.anim_names}
        self._target_w['lower'] = dict(new_t)
        self._target_w['upper'] = dict(new_t)
        if not self._hands_oneshot:
            self._target_w['hands'] = dict(new_t)
        for p in ('lower', 'upper'):
            self.ybot.play(anim_name, partName=p)
        if not self._hands_oneshot:
            self.ybot.play(anim_name, partName='hands')

        self._anim_token += 1
        token = self._anim_token
        dur = self.ybot.getDuration(anim_name)
        back_after = max(dur - 0.05, 0.05)

        def _back(task, t=token):
            if t != self._anim_token:
                return Task.done
            self.kneel_state = end_state
            # current_anim 이 transition anim 이름이라 _update_locomotion 의
            # `if target != self.current_anim` 분기에서 KneelIdle / Idle 로 자동 갱신.
            return Task.done

        self.taskMgr.doMethodLater(back_after, _back, 'kneel_transition_return')

    def _target_anim(self):
        """현재 상태(공중/무릎/이동방향)에 맞는 loop anim 이름."""
        if self.kneel_state == 'going_down' and 'StandToKneel' in self.anim_names:
            return 'StandToKneel'
        if self.kneel_state == 'going_up' and 'KneelToStand' in self.anim_names:
            return 'KneelToStand'
        if self.kneel_state == 'kneel' and 'KneelIdle' in self.anim_names:
            return 'KneelIdle'
        if not self.on_ground and 'Jump' in self.anim_names:
            return 'Jump'
        fwd = self.keys['w'] - self.keys['s']
        rgt = self.keys['d'] - self.keys['a']
        if fwd > 0 and 'RunForward' in self.anim_names:
            return 'RunForward'
        if fwd < 0 and 'RunBackward' in self.anim_names:
            return 'RunBackward'
        if rgt > 0 and 'StrafeR' in self.anim_names:
            return 'StrafeR'
        if rgt < 0 and 'StrafeL' in self.anim_names:
            return 'StrafeL'
        return 'Idle'

    def _update_locomotion(self):
        # Kneel transition 중에는 _play_kneel_transition 이 target_w 를 잡고 있음.
        # 모든 파트가 transition anim 으로 가야 하니 여기서 건드리지 않음.
        if self.kneel_state in ('going_down', 'going_up'):
            return
        target = self._target_anim()
        # Reload 중 W/S = RunForward/RunBackward 는 Mixamo anim 의 Hips pitch
        # (앞으로 숙임) 가 살아있어서 Spine→Arm→Hand 로 전파 → 권총·팔이 화면
        # 아래로 빠짐. A/D 의 StrafeL/R 은 Hips pitch 가 없어 reload 가 정상으로
        # 보이는 거. 같은 효과를 W/S 에도 주려고 lower 를 Idle 로 대체 — 다리는
        # 멈추지만 player_pos 는 그대로 전진/후진. 1인칭이라 다리는 거의 안 보임.
        if self._reload_oneshot and target in ('RunForward', 'RunBackward'):
            target = 'Idle'
        loco_w = {a: (1.0 if a == target else 0.0) for a in self.anim_names}
        # lower: 항상 locomotion. Shoot 단발 중에도 다리는 안 멈춤.
        self._target_w['lower'] = dict(loco_w)
        # upper: locomotion (단, reload 중에는 reload 가 잡고 있음).
        if not self._reload_oneshot and target != self.current_anim:
            self.current_anim = target
            self._target_w['upper'] = dict(loco_w)
        # hands: Shoot/Reload 단발 중 아니면 upper 와 동일.
        if not self._hands_oneshot and not self._reload_oneshot:
            self._target_w['hands'] = dict(self._target_w['upper'])

    def _play_shoot_oneshot(self):
        if 'Shoot' not in self.anim_names or self._hands_oneshot or self._reload_oneshot:
            return
        # hands 만 Shoot 자세로 — 다리/상체는 그대로.
        self.ybot.play('Shoot', partName='hands')
        self.recoil_back = self.recoil_shoot_back
        self.slide_recoil = self.slide_recoil_kick
        self._hands_oneshot = True
        self._target_w['hands'] = {
            a: (1.0 if a == 'Shoot' else 0.0) for a in self.anim_names
        }
        self._hands_token += 1
        token = self._hands_token
        dur = self.ybot.getDuration('Shoot')
        back_after = max(dur - self.blend_out_time, 0.05)

        def _back(task, t=token):
            if t != self._hands_token:
                return Task.done
            self._hands_oneshot = False
            # upper 의 현재 target 으로 hands 동기화.
            self._target_w['hands'] = dict(self._target_w['upper'])
            return Task.done

        self.taskMgr.doMethodLater(back_after, _back, 'hands_return')

    def _play_reload_oneshot(self):
        if ('Reload' not in self.anim_names or self._reload_oneshot
                or self.kneel_state in ('going_down', 'going_up')):
            return
        # upper + hands 두 파트만 단발 (lower 는 locomotion 유지 → 달리며 재장전)
        self.ybot.play('Reload', partName='upper')
        self.ybot.play('Reload', partName='hands')
        self._reload_oneshot = True
        rl = {a: (1.0 if a == 'Reload' else 0.0) for a in self.anim_names}
        self._target_w['upper'] = dict(rl)
        self._target_w['hands'] = dict(rl)
        self._reload_token += 1
        token = self._reload_token
        dur = self.ybot.getDuration('Reload')

        # 슬라이드 래킹 — reload 후반에 기존 slide_recoil 재사용
        def _slide_kick(task, t=token):
            if t == self._reload_token and self.slide_node is not None:
                self.slide_recoil = self.slide_recoil_kick
            return Task.done

        self.taskMgr.doMethodLater(dur * 0.88, _slide_kick, 'reload_slide_kick')

        back_after = max(dur - self.blend_out_time, 0.05)

        def _back(task, t=token):
            if t != self._reload_token:
                return Task.done
            self._reload_oneshot = False
            # upper/hands 를 다음 프레임에 locomotion 으로 강제 재평가시키는 sentinel
            self.current_anim = '__reload_done__'
            return Task.done

        self.taskMgr.doMethodLater(back_after, _back, 'reload_return')

    def _update_blend(self, dt):
        # 지수 평활: 각 파트마다 current_w 를 target_w 쪽으로 비례 수렴.
        alpha = min(1.0, dt * self.blend_speed)
        for p in self._parts:
            cur_w = self._current_w[p]
            tgt_w = self._target_w[p]
            for a in self.anim_names:
                cur = cur_w[a]
                tgt = tgt_w[a]
                if cur == tgt:
                    continue
                new = cur + (tgt - cur) * alpha
                if abs(new - tgt) < 0.001:
                    new = tgt
                cur_w[a] = new
                self.ybot.setControlEffect(a, new, partName=p)

    def _toggle_editor(self):
        self.editor_mode = not self.editor_mode
        # cursor 상태는 안 바꿈 (양쪽 다 confined+hidden = 무한 회전 가능).
        if self.editor_mode:
            # editor 진입: 현재 카메라 위치/방향에서 시작 → 시각적 점프 없음.
            self.editor_pos = Vec3(self.camera.getPos(self.render))
            self.editor_yaw = self.player_yaw
            self.editor_pitch = self.player_pitch
        self.win.movePointer(0, self._win_cx, self._win_cy)
        self._first_frame = True

    # --- pause menu ---------------------------------------------------------

    def _build_pause_menu(self):
        # 어두운 반투명 배경 + 가운데 PAUSED + Resume/Quit 두 버튼.
        self.pause_frame = DirectFrame(
            frameColor=(0, 0, 0, 0.6),
            frameSize=(-0.5, 0.5, -0.4, 0.4),
            pos=(0, 0, 0),
            parent=self.aspect2d,
        )
        OnscreenText(
            text='PAUSED', pos=(0, 0.22), scale=0.12,
            fg=(1, 1, 1, 1), align=TextNode.ACenter, mayChange=False,
            parent=self.pause_frame,
        )
        DirectButton(
            text='Resume',
            scale=0.08, pos=(0, 0, 0.0),
            command=self._toggle_pause,
            parent=self.pause_frame,
            frameSize=(-3, 3, -0.8, 1.2),
        )
        DirectButton(
            text='Quit',
            scale=0.08, pos=(0, 0, -0.22),
            command=self.userExit,
            parent=self.pause_frame,
            frameSize=(-3, 3, -0.8, 1.2),
        )
        self.pause_frame.hide()

    def _toggle_pause(self):
        self.paused = not self.paused
        props = WindowProperties()
        if self.paused:
            self.pause_frame.show()
            # cursor 보이게 + absolute 모드로 메뉴 클릭 가능.
            props.setCursorHidden(False)
            props.setMouseMode(WindowProperties.M_absolute)
            self.win.requestProperties(props)
        else:
            self.pause_frame.hide()
            # 다시 게임으로 — confined + hidden + 첫 프레임 mouse delta 무시.
            props.setCursorHidden(True)
            props.setMouseMode(WindowProperties.M_confined)
            self.win.requestProperties(props)
            self.win.movePointer(0, self._win_cx, self._win_cy)
            self._first_frame = True

    # --- debug --------------------------------------------------------------

    def _dump_joints(self, task):
        names = [j.getName() for j in self.ybot.getJoints()]
        print(f'[joint] count={len(names)}', flush=True)
        print(f'[joint] first 10: {names[:10]}', flush=True)
        wanted = ('Hips', 'Spine', 'Head', 'LeftHand', 'RightHand', 'LeftFoot', 'RightFoot')
        for tag in wanted:
            m = next((n for n in names if n.endswith(tag)), None)
            if not m:
                print(f'[joint] {tag}: not found', flush=True)
                continue
            # 본이 어느 subpart 에 속하는지 모르니 순서대로 시도.
            for part in self._parts:
                try:
                    j = self.ybot.exposeJoint(None, part, m)
                    if j is None or j.isEmpty():
                        continue
                    p = j.getPos(self.ybot)
                    print(f'[joint] {tag} [{part}] ({m}): '
                          f'({p.x:.2f}, {p.y:.2f}, {p.z:.2f})', flush=True)
                    break
                except Exception:
                    continue
        return Task.done

    # --- main loop ----------------------------------------------------------

    def _update(self, task):
        # paused: 게임 update 통째로 skip. doMethodLater 단발 anim 콜백은 계속
        # 흘러가지만 (실시간 기반) 일시정지 중에 사용자가 할 일이 거의 없으니 OK.
        if self.paused:
            return Task.cont
        dt = ClockObject.getGlobalClock().getDt()

        # 애니메이션 블렌딩 weight 수렴
        self._update_blend(dt)

        # 사격 반동 자연 감쇠 — weapon_anchor 위치에 적용 (카메라엔 영향 없음)
        decay = min(1.0, dt * self.recoil_decay)
        self.recoil_back += (0.0 - self.recoil_back) * decay
        # 슬라이드 후퇴 감쇠 + 실제 노드 위치 적용. 모델의 +X 가 권총 뒤쪽이라
        # rest 에서 +slide_recoil 만큼 더해야 뒤로 빠지는 효과.
        if self.slide_node is not None:
            sdec = min(1.0, dt * self.slide_recoil_decay)
            self.slide_recoil += (0.0 - self.slide_recoil) * sdec
            self.slide_node.setX(self.slide_rest_x + self.slide_recoil)

        # 마우스 룩 — 1인칭이면 player_yaw/pitch, editor 면 editor_yaw/pitch.
        if self.win.hasPointer(0):
            md = self.win.getPointer(0)
            dx = md.getX() - self._win_cx
            dy = md.getY() - self._win_cy
            self.win.movePointer(0, self._win_cx, self._win_cy)
            if self._first_frame:
                self._first_frame = False  # 초기화 직후 점프 방지
            elif self.editor_mode:
                self.editor_yaw -= dx * self.mouse_sens
                self.editor_pitch -= dy * self.mouse_sens
                self.editor_pitch = max(-89.0, min(89.0, self.editor_pitch))
            else:
                # 1인칭은 좌우(yaw)만 — 상하 시점은 고정 (편의 / 멀미 방지).
                # editor (F2 free-cam) 모드에선 위아래도 가능.
                self.player_yaw -= dx * self.mouse_sens

        if self.editor_mode:
            # editor free-cam: 카메라가 보는 방향 + 우 + 위. Space=상, 잠금 없음.
            yr = radians(self.editor_yaw)
            pr = radians(self.editor_pitch)
            forward = Vec3(-sin(yr) * cos(pr), cos(yr) * cos(pr), sin(pr))
            right_v = Vec3(cos(yr), sin(yr), 0)
            mv = Vec3(0, 0, 0)
            if self.keys['w']: mv += forward
            if self.keys['s']: mv -= forward
            if self.keys['d']: mv += right_v
            if self.keys['a']: mv -= right_v
            if self.keys['space']: mv += Vec3(0, 0, 1)
            if mv.length() > 0:
                mv.normalize()
                self.editor_pos += mv * (self.editor_speed * dt)
        else:
            # WASD 이동 + 점프 (1인칭, 서있는 상태에서만 — 무릎/transition 중 잠금)
            if self.kneel_state == 'stand':
                yr = radians(self.player_yaw)
                forward = Vec3(-sin(yr), cos(yr), 0)
                right_v = Vec3(cos(yr), sin(yr), 0)
                mv = Vec3(0, 0, 0)
                if self.keys['w']: mv += forward
                if self.keys['s']: mv -= forward
                if self.keys['d']: mv += right_v
                if self.keys['a']: mv -= right_v
                if mv.length() > 0:
                    mv.normalize()
                    self.player_pos += mv * (self.move_speed * dt)
                if self.keys['space'] and self.on_ground:
                    self.player_vz = self.jump_speed
                    self.on_ground = False

            # 중력은 항상 적용 (무릎자세에서도)
            self.player_vz -= self.gravity * dt
            self.player_pos.z += self.player_vz * dt
            if self.player_pos.z <= 0:
                self.player_pos.z = 0
                self.player_vz = 0
                self.on_ground = True

        # 현재 상태에 맞는 locomotion anim 선택
        self._update_locomotion()

        # 캐릭터 트랜스폼 동기화 (+ Hips XY anchor 보정 + 사격 반동 뒤로 이동).
        # 사격 반동은 캐릭터 전체를 카메라 forward 의 반대 방향으로 살짝 밀어서
        # 팔·손·권총 다 같이 뒤로 빠지게. 카메라는 아래쪽에서 보정해서 시점은 고정.
        yr_recoil = radians(self.player_yaw)
        fwd_recoil = Vec3(-sin(yr_recoil), cos(yr_recoil), 0)
        recoil_offset = fwd_recoil * (-self.recoil_back)

        # Walk bob (Z) — reload 중 + 이동키 눌렸을 때만 ramp in. 카메라에서 같은
        # bob_z 를 빼서 화면은 정적, 자기 몸·팔·총만 까딱.
        moving = any(self.keys[k] for k in ('w', 'a', 's', 'd'))
        target_bob = 1.0 if (self._reload_oneshot and moving) else 0.0
        self._walk_bob_t += ((target_bob - self._walk_bob_t)
                             * min(1.0, dt * self._walk_bob_speed))
        if self._walk_bob_t > 0.001:
            self._walk_bob_phase += dt * self._walk_bob_freq
        else:
            self._walk_bob_phase = 0.0
        bob_z = (self._walk_bob_amp_z * self._walk_bob_t
                 * sin(self._walk_bob_phase))

        self.ybot.setPos(self.player_pos + recoil_offset + Vec3(0, 0, bob_z))
        self.ybot.setH(self.player_yaw + 180)
        # 애니메이션을 현재 시각으로 강제 동기화. 안 하면 joint 의 world 좌표가
        # 1프레임 lag 된 상태를 반환해서 카메라가 머리에서 떨림.
        self.ybot.update(force=True)
        if self.hips_joint is not None:
            local = self.hips_joint.getPos(self.ybot)
            if self._hips_ref_local is None:
                self._hips_ref_local = Vec3(local)
            dlx = self._hips_ref_local.x - local.x
            dly = self._hips_ref_local.y - local.y
            h_rad = radians(self.ybot.getH())
            c, s = cos(h_rad), sin(h_rad)
            self.ybot.setX(self.ybot.getX() + c * dlx - s * dly)
            self.ybot.setY(self.ybot.getY() + s * dlx + c * dly)

        # weapon anchor 갱신: hand 본 따라감. ybot 자체가 사격 반동으로 뒤로 가서
        # hand 본 world 좌표도 자동으로 뒤로 — 추가 offset 불필요.
        if (self.weapon is not None
                and self.right_hand_joint is not None
                and not self.right_hand_joint.isEmpty()):
            self.weapon_anchor.setPos(self.right_hand_joint.getPos(self.render))
            self.weapon_anchor.setHpr(self.right_hand_joint.getHpr(self.render))

        # 카메라 배치
        if self.editor_mode:
            # free-cam: editor_pos / editor_yaw / pitch 그대로 사용
            self.camera.setPos(self.editor_pos)
            self.camera.setHpr(self.editor_yaw, self.editor_pitch, 0)
        else:
            # 카메라를 Head 본 월드 좌표에 부착. 머리 애니메이션 그대로 따라감.
            # 시선 방향(yaw/pitch) 은 마우스 입력 그대로 — head 본의 회전은 무시.
            # 사격 반동(recoil_pitch/back)은 매 프레임 감쇠되며 카메라에 가산.
            if self.head_joint is not None:
                head_w = self.head_joint.getPos(self.render)
                yr = radians(self.player_yaw)
                forward = Vec3(-sin(yr), cos(yr), 0)
                right_v = Vec3(cos(yr), sin(yr), 0)
                # 카메라 시점 고정: ybot 이 recoil_back 만큼 뒤로 가서 head_w 도
                # 같이 뒤로 가있는 상태. +forward * recoil_back 으로 보정 → 카메라
                # 절대 위치는 사격 전과 동일.
                # left lateral offset 추가 → 권총·손이 화면 우측에 보임 (FPS 표준).
                self.camera.setPos(
                    head_w
                    + forward * (self.eye_forward_offset + self.recoil_back)
                    - right_v * self.eye_lateral_offset
                    - Vec3(0, 0, bob_z)   # ybot 의 Z bob 상쇄 → 카메라 정적
                )
            else:
                self.camera.setPos(self.player_pos + Vec3(0, 0, self.head_height))
            self.camera.setHpr(self.player_yaw, self.player_pitch, 0)

        # HUD
        fps = ClockObject.getGlobalClock().getAverageFrameRate()
        self.hud.setText(
            f'anim:  {self.current_anim}'
            f'{"  +Shoot(hands)" if self._hands_oneshot else ""}'
            f'{"  +Reload(upper)" if self._reload_oneshot else ""}\n'
            f'fps:   {fps:.0f}\n'
            f'pos:   ({self.player_pos.x:.1f}, {self.player_pos.y:.1f}, {self.player_pos.z:.1f})\n'
            f'mode:  {"editor[F2]" if self.editor_mode else "fps"}'
            f'{"  KNEEL" if self.kneel_state == "kneel" else ""}'
            f'{"  KNEEL->" if self.kneel_state == "going_down" else ""}'
            f'{"  STAND->" if self.kneel_state == "going_up" else ""}'
        )

        return Task.cont


if __name__ == '__main__':
    ZombieGame().run()
