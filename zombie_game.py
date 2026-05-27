"""
zombie_game — Mirror's Edge style 1인칭 좀비 슈터 (Panda3D)
Stage 1: 1인칭 카메라 + Y Bot 풀바디 + 기본 입력.
"""
import random
from math import cos, radians, sin
from pathlib import Path

from direct.actor.Actor import Actor
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from panda3d.core import (
    AmbientLight, CardMaker, ClockObject, DirectionalLight, Filename,
    NodePath, TextNode, Vec3, Vec4, WindowProperties,
)


SCRIPT_DIR = Path(__file__).parent
BAM_PATH = Filename.from_os_specific(
    str(SCRIPT_DIR / 'assets' / 'ybot' / 'scene.bam')
)


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
        # 블렌딩 모드: 여러 애니메이션을 동시에 돌리면서 weight 로 섞는다.
        # Unity 의 crossfade 와 동일한 효과 — 액션 전환 시 움찔거림 제거.
        self.ybot.enableBlend()
        if 'Idle' in self.anim_names:
            self.ybot.loop('Idle')
        self.current_anim = 'Idle'
        self._anim_token = 0
        # 각 애니메이션의 현재 weight, 목표 weight. _update_blend 가 매 프레임
        # 지수 평활로 current → target 수렴시킨다.
        self._current_w = {a: (1.0 if a == 'Idle' else 0.0) for a in self.anim_names}
        self._target_w = dict(self._current_w)
        for a, w in self._current_w.items():
            self.ybot.setControlEffect(a, w)
        self.blend_speed = 14.0       # 크면 빠른 전환, 작으면 부드러움
        self.blend_out_time = 0.18    # 단발 anim 끝나기 이만큼 전부터 다음 상태로 페이드

        # 모든 locomotion anim 을 항상 loop 시켜둠 — weight 가 0 이어도 내부 time 은
        # 흐르고, 보이는 건 _current_w 가 결정. 액션 전환 시 시작 프레임이 갑자기
        # 튀지 않게 함.
        self._loop_anim_set = {
            'Idle', 'RunForward', 'RunBackward', 'StrafeL', 'StrafeR',
            'KneelIdle', 'Jump',
        }
        for a in self.anim_names:
            if a in self._loop_anim_set:
                self.ybot.loop(a)

        # Ctrl 로 토글되는 무릎 자세
        self.kneel_mode = False

        # 사격 반동 (Shoot 모션에는 팔이 안 움직이므로 카메라로 시뮬레이션)
        self.recoil_pitch = 0.0          # 위로 킥
        self.recoil_back = 0.0           # 뒤로 살짝
        self.recoil_decay = 9.0          # 1/sec, 클수록 빨리 가라앉음
        self.recoil_shoot_pitch = 5.5    # 발사 시 인가되는 pitch (도)
        self.recoil_shoot_back = 0.05    # 발사 시 인가되는 뒤로 오프셋 (m)

        # Hips root motion 상쇄용. Mixamo 머지 .bam 은 각 액션의 Hips 시작 위치가
        # 미묘하게 달라서 (예: Idle Y=-0.944, Shoot Y=-0.892) 액션 전환 시 캐릭터
        # 전체가 5cm 가량 카메라 방향으로 평행이동 → 머리가 카메라 안으로 밀려들어와
        # 뒤통수가 화면을 덮음. 매 프레임 Hips 의 actor-local XY drift 를 측정해서
        # actor NodePath 를 반대로 밀어줘서 시각적 anchor 를 고정한다. Z(높이) 는
        # 그대로 둬서 Punch 의 자연스러운 body bob 은 유지.
        hips_name = next(
            (j.getName() for j in self.ybot.getJoints() if j.getName().endswith('Hips')),
            None,
        )
        head_name = next(
            (j.getName() for j in self.ybot.getJoints() if j.getName().endswith('Head')),
            None,
        )
        print(f'[zombie_game] hips/head joints: {hips_name} / {head_name}', flush=True)
        self.hips_joint = (
            self.ybot.exposeJoint(None, 'modelRoot', hips_name) if hips_name else None
        )
        self.head_joint = (
            self.ybot.exposeJoint(None, 'modelRoot', head_name) if head_name else None
        )
        self._hips_ref_local = None  # Idle 첫 프레임에서 자동 캡처
        # 카메라를 Head 본의 월드 좌표에 매 프레임 따라붙임. 머리가 애니메이션으로
        # 흔들려도 카메라가 동행하니까 자기 뒤통수가 보이는 일이 없음.
        # 시선 방향(yaw/pitch)은 마우스 입력 그대로 — head 본의 회전은 무시.
        self.eye_forward_offset = 0.22  # 머리 본 중심에서 시선 방향으로 m (몸 멀리 보이게)

        # 입력
        self.keys = {'w': False, 'a': False, 's': False, 'd': False, 'space': False}
        self.editor_mode = False
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
        self.accept('escape', self.userExit)
        self.accept('mouse1', self._play_oneshot, ['Shoot'])
        self.accept('f', self._play_oneshot, ['Punch'])
        self.accept('f2', self._toggle_editor)
        # Ctrl 토글 — OS/키맵에 따라 이벤트명이 다를 수 있어서 셋 다 bind
        for k in ('control', 'lcontrol', 'rcontrol'):
            self.accept(k, self._toggle_kneel)

    def _set_key(self, k, v):
        self.keys[k] = v

    def _toggle_kneel(self):
        self.kneel_mode = not self.kneel_mode

    def _target_anim(self):
        """현재 상태(공중/무릎/이동방향)에 맞는 loop anim 이름."""
        if not self.on_ground and 'Jump' in self.anim_names:
            return 'Jump'
        if self.kneel_mode and 'KneelIdle' in self.anim_names:
            return 'KneelIdle'
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
        # Shoot/Punch 같은 단발이 도는 중이면 건드리지 않음 — _back 콜백이 끝낼 때
        # 알아서 현재 상태에 맞는 anim 으로 복귀.
        if self.current_anim in ('Shoot', 'Punch'):
            return
        target = self._target_anim()
        if target != self.current_anim:
            self.current_anim = target
            self._target_w = {a: (1.0 if a == target else 0.0) for a in self.anim_names}

    def _play_oneshot(self, name):
        if name not in self.anim_names:
            return
        # 같은 단발이 이미 재생 중이면 무시 — 연타로 끊기지 않게.
        if self.current_anim == name:
            return
        # 단발 anim 을 0번 프레임부터 재생하고 target weight 를 그쪽으로 옮기면
        # _update_blend 가 부드럽게 crossfade.
        self.ybot.play(name)
        if name == 'Shoot':
            # 위로 + 뒤로 카메라 킥. 자연 감쇠로 다시 가라앉음.
            self.recoil_pitch = self.recoil_shoot_pitch
            self.recoil_back = self.recoil_shoot_back
        self.current_anim = name
        self._target_w = {a: (1.0 if a == name else 0.0) for a in self.anim_names}
        self._anim_token += 1
        token = self._anim_token
        dur = self.ybot.getDuration(name)
        back_after = max(dur - self.blend_out_time, 0.05)

        def _back(task, t=token):
            if t != self._anim_token:
                return Task.done  # 그 사이에 새 oneshot 이 시작됨, 무시
            # 현재 상태(이동/무릎/공중)에 맞는 anim 으로 복귀
            target = self._target_anim()
            self.current_anim = target
            self._target_w = {a: (1.0 if a == target else 0.0) for a in self.anim_names}
            return Task.done

        self.taskMgr.doMethodLater(back_after, _back, 'return_idle')

    def _update_blend(self, dt):
        # 지수 평활: current_w 를 매 프레임 target_w 쪽으로 비례 수렴.
        alpha = min(1.0, dt * self.blend_speed)
        for a in self.anim_names:
            cur = self._current_w[a]
            tgt = self._target_w[a]
            if cur == tgt:
                continue
            new = cur + (tgt - cur) * alpha
            # 거의 다 왔으면 스냅(불필요한 setControlEffect 호출 줄임)
            if abs(new - tgt) < 0.001:
                new = tgt
            self._current_w[a] = new
            self.ybot.setControlEffect(a, new)

    def _toggle_editor(self):
        self.editor_mode = not self.editor_mode
        props = WindowProperties()
        props.setCursorHidden(not self.editor_mode)
        props.setMouseMode(
            WindowProperties.M_absolute if self.editor_mode
            else WindowProperties.M_confined
        )
        self.win.requestProperties(props)
        if not self.editor_mode:
            # 1인칭 복귀 시 첫 프레임 mouse delta 무시
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
            j = self.ybot.exposeJoint(None, 'modelRoot', m)
            p = j.getPos(self.ybot)
            print(f'[joint] {tag} ({m}): ({p.x:.2f}, {p.y:.2f}, {p.z:.2f})', flush=True)
        return Task.done

    # --- main loop ----------------------------------------------------------

    def _update(self, task):
        dt = ClockObject.getGlobalClock().getDt()

        # 애니메이션 블렌딩 weight 수렴
        self._update_blend(dt)

        # 사격 반동 자연 감쇠 (지수)
        decay = min(1.0, dt * self.recoil_decay)
        self.recoil_pitch += (0.0 - self.recoil_pitch) * decay
        self.recoil_back += (0.0 - self.recoil_back) * decay

        # 마우스 룩 (1인칭만)
        if not self.editor_mode and self.win.hasPointer(0):
            md = self.win.getPointer(0)
            dx = md.getX() - self._win_cx
            dy = md.getY() - self._win_cy
            self.win.movePointer(0, self._win_cx, self._win_cy)
            if self._first_frame:
                self._first_frame = False  # 초기화 직후 점프 방지
            else:
                self.player_yaw -= dx * self.mouse_sens
                self.player_pitch -= dy * self.mouse_sens
                self.player_pitch = max(-89.0, min(89.0, self.player_pitch))

        # WASD 이동 + 점프 (1인칭, 무릎자세 아닐 때만)
        if not self.editor_mode:
            if not self.kneel_mode:
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

        # 현재 상태에 맞는 locomotion anim 선택 (Shoot/Punch 단발 중이면 skip)
        self._update_locomotion()

        # 캐릭터 트랜스폼 동기화 (+ Hips XY anchor 보정)
        self.ybot.setPos(self.player_pos)
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

        # 카메라 배치
        if self.editor_mode:
            # 3인칭 디버그: 플레이어 뒤+위에서 캐릭터 응시
            yr = radians(self.player_yaw)
            cam_offset = Vec3(sin(yr) * 4.0, -cos(yr) * 4.0, 2.0)
            self.camera.setPos(self.player_pos + cam_offset)
            self.camera.lookAt(self.player_pos + Vec3(0, 0, 1.2))
        else:
            # 카메라를 Head 본의 월드 좌표에 부착. 머리 애니메이션을 그대로 따라감.
            # 시선 방향(yaw/pitch)은 마우스 입력 기반 — head 본의 회전은 무시.
            # 사격 반동(recoil_pitch/back)은 매 프레임 감쇠되며 카메라에 가산.
            if self.head_joint is not None:
                head_w = self.head_joint.getPos(self.render)
                yr = radians(self.player_yaw)
                forward = Vec3(-sin(yr), cos(yr), 0)
                cam_forward_offset = self.eye_forward_offset - self.recoil_back
                self.camera.setPos(head_w + forward * cam_forward_offset)
            else:
                self.camera.setPos(self.player_pos + Vec3(0, 0, self.head_height))
            self.camera.setHpr(
                self.player_yaw,
                self.player_pitch + self.recoil_pitch,
                0,
            )

        # HUD
        fps = ClockObject.getGlobalClock().getAverageFrameRate()
        self.hud.setText(
            f'anim:  {self.current_anim}\n'
            f'fps:   {fps:.0f}\n'
            f'pos:   ({self.player_pos.x:.1f}, {self.player_pos.y:.1f}, {self.player_pos.z:.1f})\n'
            f'mode:  {"editor[F2]" if self.editor_mode else "fps"}'
            f'{"  KNEEL[Ctrl]" if self.kneel_mode else ""}'
        )

        return Task.cont


if __name__ == '__main__':
    ZombieGame().run()
