"""
zombie_game — Mirror's Edge style 1인칭 좀비 슈터
Stage 1: 1인칭 카메라 + Y Bot 풀바디 + 기본 입력
"""
from pathlib import Path

from direct.actor.Actor import Actor
from panda3d.core import Filename

from ursina import (
    Ursina, Entity, EditorCamera, Text, Sky, Vec2,
    application, camera, color, held_keys, invoke, mouse, random, scene, time, window,
)
from ursina.prefabs.first_person_controller import FirstPersonController


SCRIPT_DIR = Path(__file__).parent
BAM_PATH = Filename.from_os_specific(
    str(SCRIPT_DIR / 'assets' / 'ybot' / 'scene.bam')
)

app = Ursina()
window.title = 'zombie_game'
window.exit_button.visible = False
window.fps_counter.visible = False

# 카메라가 캐릭터 머리 내부에 있어도 자기 몸이 보이도록 near plane 매우 작게
camera.clip_plane_near = 0.01

# 환경
Entity(
    model='plane', scale=64,
    texture='white_cube', texture_scale=(64, 64),
    color=color.gray, collider='box',
)
for _ in range(12):
    Entity(
        model='cube',
        color=color.azure,
        position=(random.uniform(-15, 15), 0.5, random.uniform(-15, 15)),
        collider='box',
    )
Sky()

# 플레이어
player = FirstPersonController(
    position=(0, 1, 0),
    speed=6,
    jump_height=1.5,
)
# Y Bot은 약 1.8m. 카메라를 머리 안쪽으로 내려서 아래 보면 자기 몸이 보이게.
player.camera_pivot.y = 1.65

# Y Bot Actor를 player의 자식으로 부착
ybot = Actor(BAM_PATH)
ybot.reparent_to(player)
# Mixamo Y Bot은 보통 -Z를 향함 → player forward(+Z)에 맞추기 위해 H=180.
# 누워있거나 뒤집혀 보이면 set_hpr(180, 0, 0) 의 P/R 을 조정.
ybot.set_hpr(180, 0, 0)
ybot.set_pos(0, 0, 0)

anim_names = ybot.getAnimNames()
print(f'[zombie_game] animations: {anim_names}', flush=True)
if 'Idle' in anim_names:
    ybot.loop('Idle')

# 진단: 모든 조인트 이름 + Idle 적용 후 주요 본의 ybot-local 좌표 한 번 출력.
# Mixamo 는 보통 'mixamorig:Hips' 식으로 prefix 가 붙음.
# 팔이 옆으로 뻗어있으면(T-pose 잔존) LeftHand 의 X 절대값이 약 0.7~0.9.
# 정상 Idle 이면 LeftHand 의 X 절대값이 약 0.2~0.3, 높이(panda Z) 0.7~0.9.
def _dump_joints():
    all_joints = [j.getName() for j in ybot.getJoints()]
    print(f'[joint] count={len(all_joints)}', flush=True)
    print(f'[joint] first 10: {all_joints[:10]}', flush=True)
    wanted = ('Hips', 'Spine', 'Head', 'LeftHand', 'RightHand', 'LeftFoot', 'RightFoot')
    for tag in wanted:
        match = next((n for n in all_joints if n.endswith(tag)), None)
        if not match:
            print(f'[joint] {tag}: not found', flush=True)
            continue
        j = ybot.exposeJoint(None, 'modelRoot', match)
        p = j.getPos(ybot)
        print(f'[joint] {tag} ({match}): ({p.x:.2f}, {p.y:.2f}, {p.z:.2f})', flush=True)
invoke(_dump_joints, delay=0.3)

# --- 애니메이션 상태 (단발 재생 후 Idle 자동 복귀) ---
current_anim = 'Idle'
_anim_token = 0  # 키 연타 시 이전 invoke가 늦게 발화해도 무시하기 위한 토큰


def play_oneshot(name):
    global current_anim, _anim_token
    if name not in anim_names:
        return
    ybot.stop()
    ybot.play(name)
    current_anim = name
    _anim_token += 1
    invoke(_return_to_idle, _anim_token, delay=ybot.getDuration(name))


def _return_to_idle(token):
    global current_anim
    if token != _anim_token:
        return
    if 'Idle' in anim_names:
        ybot.stop()
        ybot.loop('Idle')
    current_anim = 'Idle'


# 디버그용 3인칭 카메라 (F2로 토글). player.enabled=False 로 끄면 자식 ybot 까지 hide
# 되니까, player 의 update 만 일시정지하고 visible 은 유지한다. FPC가 camera를 자기
# camera_pivot에 reparent해놨기 때문에 camera.parent도 직접 옮겨야 시점이 바뀜.
editor_cam = EditorCamera(enabled=False)

_fpc_orig_update = player.update
_fpc_paused = {'v': False}


def _fpc_update_guarded():
    if _fpc_paused['v']:
        return
    _fpc_orig_update()


player.update = _fpc_update_guarded


def _toggle_editor():
    to_editor = not editor_cam.enabled
    editor_cam.enabled = to_editor
    _fpc_paused['v'] = to_editor
    if to_editor:
        editor_cam.world_position = player.world_position + (0, 1.5, 0)
        camera.parent = editor_cam
        camera.position = (0, 1, -4)
        camera.rotation = (10, 0, 0)
        mouse.locked = False
        mouse.visible = True
    else:
        camera.parent = player.camera_pivot
        camera.position = (0, 0, 0)
        camera.rotation = (0, 0, 0)
        mouse.locked = True
        mouse.visible = False


# HUD
hud = Text(
    text='',
    position=window.top_left + Vec2(0.02, -0.02),
    origin=(-0.5, 0.5),
    scale=0.9,
    background=True,
)


def input(key):
    if key == 'escape':
        application.quit()
    elif key == 'f2':
        _toggle_editor()
    elif key == 'left mouse down':
        play_oneshot('Shoot')
    elif key == 'f':
        play_oneshot('Punch')


def update():
    fps = int(1 / time.dt) if time.dt > 0 else 0
    p = player.position
    hud.text = (
        f'anim: {current_anim}\n'
        f'fps:  {fps}\n'
        f'pos:  ({p.x:.1f}, {p.y:.1f}, {p.z:.1f})'
    )


app.run()
