"""FPS 게임 진입점.

실행:
  - 프로젝트 루트에서 `python -m src.main`
  - 또는 `python src/main.py`  (아래 부트스트랩이 sys.path와 __package__를 보정)
"""

# `python src/main.py`로 직접 실행 시, src의 부모가 sys.path에 없어서
# 상대 임포트가 깨지므로 부트스트랩으로 보정한다.
if __name__ == "__main__" and __package__ in (None, ""):
    import os
    import sys

    _PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)
    __package__ = "src"

import simplepbr
from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    AmbientLight,
    CardMaker,
    ClockObject,
    DirectionalLight,
    Filename,
    Material,
    SamplerState,
    TextNode,
    Texture,
    TextureStage,
    Vec3,
    Vec4,
    WindowProperties,
    loadPrcFileData,
)
from simplepbr.envmap import EnvMap
from simplepbr.utils import make_skybox

# ShowBase.__init__ 호출 *전* 에 prc 설정. depth 24 강제 + vsync. MSAA 는 simplepbr.init
# 의 msaa_samples 인자로 따로 처리. framebuffer-srgb 는 simplepbr 가 자체 톤매핑/감마를
# 처리하므로 직접 안 건드림.
loadPrcFileData("", "framebuffer-depth-bits 24")
loadPrcFileData("", "sync-video 1")

from .cubemap import equirect_to_cubemap
from .level_up import LevelUpManager, LevelUpScreen, xp_to_next
from .physics import GROUND_MASK, HITTABLE_MASK
from .player import PlayerController
from .settings_menu import SettingsMenu
from .start_screen import StartScreen
from .ui import HUD
from .weapons import Pistol
from .zombie import ZombieManager


_clock = ClockObject.getGlobalClock()


# 게임 플레이 영역 — WAVE_SPAWN_X/Y_RANGE 가 ±11 정도라 ±30 평면이면 충분.
_GROUND_HALF = 30.0
# Ground 텍스처 타일링 — 1 unit ≈ 1m 기준 (60m × 60m / 20 타일 = 한 타일 3m).
# 너무 크면 흐릿하고 너무 작으면 패턴 반복이 눈에 띔.
_GROUND_TILES = 20


class FPSGame(ShowBase):
    def __init__(self):
        super().__init__()

        # ---- 1. simplepbr 활성화 ----
        # ShowBase 직후, camLens 설정 전에 PBR 파이프라인 부착. simplepbr 가 자체 GLSL
        # 셰이더를 박으므로 render.setShaderAuto() 를 직접 호출하면 안 된다.
        # - use_normal_maps / emission_maps: PBR 텍스처 셋의 노멀/이미시브 채널 활성
        # - enable_shadows: DirectionalLight.setShadowCaster 가 실제로 그림자 생성
        # - msaa_samples=4: 후처리 단계 안티앨리어싱 (prc multisamples 가 아니라 simplepbr
        #   내부 buffer 에서 처리 — RTX 50 시리즈 + Panda 1.10 의 fb-MSAA 깨짐 회피)
        # - exposure: EV stop (2**exposure 배). 0.0 = 중립, +1 = 2배, -1 = 0.5배.
        #   Last of Us 풍 어두운 폐허 톤이라 -1.5 (≈ 0.35배) — puresky HDRI 의 밝은 하늘이
        #   IBL 로 씬을 밝히는 양을 상쇄. 너무 밝으면 더 음수, 너무 어두우면 0 쪽으로.
        self.pbr_pipeline = simplepbr.init(
            use_normal_maps=True,
            use_emission_maps=True,
            enable_shadows=True,
            msaa_samples=4,
            max_lights=8,
            exposure=-2.5,
        )

        # 1인칭 무기는 카메라에서 ~0.9m 근처 → near=0.1 안전. far=200 으로 둬 far/near
        # ratio 2000 이하 유지 (24-bit depth 도 ratio 가 너무 크면 정밀도 깨짐).
        self.camLens.setNear(0.1)
        self.camLens.setFar(200.0)

        # 백버퍼/깊이/스텐실 매 프레임 강제 클리어 — 새 GPU/드라이버 조합에서 이전 프레임이
        # 누적되어 잔상으로 보이는 사고 회피. skybox 로딩 실패 fallback 용 어두운 회청색.
        self.win.setClearColorActive(True)
        self.win.setClearDepthActive(True)
        self.win.setClearStencilActive(True)
        self.setBackgroundColor(0.08, 0.10, 0.13, 1.0)

        # ---- 2. 한글 폰트 ----
        try:
            font_path = Filename.fromOsSpecific(
                "C:/Windows/Fonts/malgun.ttf"
            ).getFullpath()
            kr_font = self.loader.loadFont(font_path)
            if kr_font is not None and kr_font.isValid():
                kr_font.setPixelsPerUnit(60)
                TextNode.setDefaultFont(kr_font)
        except (OSError, IOError):
            pass

        # ---- 3. IBL + Skybox ----
        # cloudy_vondelpark 1K equirectangular HDR → in-memory cubemap (cubemap.py).
        # simplepbr 0.13.1 의 EnvMap.from_file_path 는 #-치환 6 face 경로나 DDS cubemap 만
        # 받기 때문에 polyhaven 식 equirect 단일 파일은 직접 변환해서 EnvMap 생성자에
        # 텍스처로 넘긴다. spherical harmonics + prefiltered cubemap 은 EnvMap 이
        # 내부에서 계산. blocking_prepare 로 동기 완료해 첫 프레임에 환경맵 보장.
        self.skybox = None
        try:
            hdri_path = _assets_root() / "hdri" / "sky.hdr"
            # face_size=256: 1K equirect (1024×512) 를 face 당 256² 으로 샘플 — 약 4 초
            # 변환. 128 은 skybox 가 너무 흐릿하게 보였고, 512 는 부팅 시간이 길어짐.
            cubemap = equirect_to_cubemap(hdri_path, face_size=256)
            self.env_map = EnvMap(cubemap, blocking_prepare=True)
            self.pbr_pipeline.env_map = self.env_map
            self.skybox = make_skybox(cubemap)
            self.skybox.reparentTo(self.render)
        except Exception as e:  # noqa: BLE001
            print(
                f"[render] IBL/skybox setup failed — fallback to background color: {e}",
                flush=True,
            )

        # ---- 4. 지면 ----
        # models/environment 의 UV 가 PBR 타일링에 맞지 않아 CardMaker 평면으로 교체.
        # XY 평면(Z=0) 에 깔린 60m × 60m. CardMaker 가 기본 XZ 평면이라 setP(-90) 으로 눕힘.
        cm = CardMaker("ground")
        cm.setFrame(-_GROUND_HALF, _GROUND_HALF, -_GROUND_HALF, _GROUND_HALF)
        self.ground = self.render.attachNewNode(cm.generate())
        self.ground.setP(-90)

        # PBR 텍스처 부착
        #   - albedo: TextureStage 기본 모드(MModulate) → simplepbr base color 입력
        #   - normal: TextureStage.MNormal → simplepbr 가 noraml mapping 으로 인식
        # roughness/AO 도 다운로드해 두지만 simplepbr 0.13 은 ORM(R=AO/G=roughness/M=metallic)
        # 패킹된 단일 텍스처를 기대해서 1 채널 분리본을 그대로는 못 쓴다. 향후 ORM 패킹
        # 헬퍼를 만들 때까지 Material 의 roughness 만 fallback 으로 사용.
        textures_root = _assets_root() / "textures" / "ground"
        albedo = self.loader.loadTexture(
            Filename.fromOsSpecific(str(textures_root / "ground_albedo.jpg"))
        )
        albedo.setWrapU(SamplerState.WM_repeat)
        albedo.setWrapV(SamplerState.WM_repeat)
        ts_albedo = TextureStage("ground_albedo")  # default 모드 = MModulate
        self.ground.setTexture(ts_albedo, albedo)
        self.ground.setTexScale(ts_albedo, _GROUND_TILES, _GROUND_TILES)

        normal = self.loader.loadTexture(
            Filename.fromOsSpecific(str(textures_root / "ground_normal.jpg"))
        )
        normal.setWrapU(SamplerState.WM_repeat)
        normal.setWrapV(SamplerState.WM_repeat)
        ts_normal = TextureStage("ground_normal")
        ts_normal.setMode(TextureStage.MNormal)
        self.ground.setTexture(ts_normal, normal)
        self.ground.setTexScale(ts_normal, _GROUND_TILES, _GROUND_TILES)

        # Material — 텍스처 base color 와 곱해지므로 흰색. metallic 0, roughness 1.0.
        ground_mat = Material("ground_pbr")
        ground_mat.setBaseColor(Vec4(1, 1, 1, 1))
        ground_mat.setMetallic(0.0)
        ground_mat.setRoughness(1.0)
        self.ground.setMaterial(ground_mat)

        # 충돌 마스크 — 플레이어 ground ray (GROUND_MASK) + 권총 raycast (HITTABLE_MASK).
        self.ground.setCollideMask(GROUND_MASK | HITTABLE_MASK)

        # ---- 5. 조명 ----
        # Last of Us 풍 흐린 톤 — 색온도 낮춘 따뜻한 키 + 푸르스름한 fill + 매우 약한 ambient.
        # IBL (env_map) 이 이미 ambient/diffuse 환경 항을 채우므로 AmbientLight 는 중첩이
        # 안 되도록 아주 낮게 (이전 0.15~0.20 은 IBL 위에 얹혀 화면 wash-out 의 원인).
        ambient = AmbientLight("scene_ambient")
        ambient.setColor(Vec4(0.04, 0.045, 0.05, 1))
        self.render.setLight(self.render.attachNewNode(ambient))

        key_light = DirectionalLight("scene_key")
        key_light.setColor(Vec4(0.27, 0.25, 0.21, 1))
        key_light.setShadowCaster(True, 1024, 1024)
        key_light.getLens().setFilmSize(40, 40)
        key_light.getLens().setNearFar(0.1, 100)
        self.key_light_np = self.render.attachNewNode(key_light)
        self.key_light_np.setHpr(-45, -30, 0)
        self.render.setLight(self.key_light_np)

        fill_light = DirectionalLight("scene_fill")
        fill_light.setColor(Vec4(0.05, 0.06, 0.09, 1))
        self.fill_light_np = self.render.attachNewNode(fill_light)
        self.fill_light_np.setHpr(135, 60, 0)
        self.render.setLight(self.fill_light_np)

        # ---- 6. 무기 전용 라이트 (카메라 자식) ----
        # 카메라가 어디를 보든 무기/손에 일정한 음영을 보장. 씬 전체에 setLight 하면
        # 환경 라이팅이 카메라 회전 따라 흔들리므로 pistol.np 노드에만 한정해 적용 (아래).
        weapon_key = DirectionalLight("weapon_key")
        weapon_key.setColor(Vec4(0.7, 0.65, 0.6, 1))
        self.weapon_key_np = self.camera.attachNewNode(weapon_key)
        self.weapon_key_np.setHpr(-30, -20, 0)

        weapon_fill = AmbientLight("weapon_fill")
        weapon_fill.setColor(Vec4(0.25, 0.27, 0.30, 1))
        self.weapon_fill_np = self.camera.attachNewNode(weapon_fill)

        # ---- 7. 게임 상태/엔티티 ----
        self.paused = False
        self.started = False
        self.level_up_active = False

        # 부팅 직후 — 시작 화면 버튼 클릭용 커서/절대 모드.
        props = WindowProperties()
        props.setCursorHidden(False)
        props.setMouseMode(WindowProperties.M_absolute)
        self.win.requestProperties(props)

        self.player = PlayerController(self)
        self.hud = HUD(self)
        self.hud.hide_gameplay()
        self.pistol = Pistol(self)

        # 무기 라이트는 pistol.np 서브트리에만 — 자식인 hands 도 자동 상속.
        self.pistol.np.setLight(self.weapon_key_np)
        self.pistol.np.setLight(self.weapon_fill_np)

        self.zombies = ZombieManager(self)

        self.level_up = LevelUpManager(self)
        self.level_up_screen = LevelUpScreen(self)
        self.hud.set_xp(self.level_up.level, self.level_up.xp,
                        xp_to_next(self.level_up.level))

        self.settings_menu = SettingsMenu(self)
        self.start_screen = StartScreen(self)

        self.accept("escape", self._toggle_pause)
        self.accept("mouse1", self._on_mouse1)
        self.accept("mouse3", self._on_mouse3, [True])
        self.accept("mouse3-up", self._on_mouse3, [False])
        self.accept("r", self._on_reload)

        self.taskMgr.add(self._weapons_update_task, "weapons_update")

        # 렌더 파이프라인 진단 — depth bits, GPU/드라이버, PBR 활성 여부.
        gsg = self.win.getGsg()
        fb = self.win.getFbProperties()
        print(
            f"GSG: {gsg.getDriverVendor()} / {gsg.getDriverRenderer()} / "
            f"depth bits: {fb.getDepthBits()} / "
            f"simplepbr msaa: {self.pbr_pipeline.msaa_samples} / "
            f"shadows: {self.pbr_pipeline.enable_shadows}",
            flush=True,
        )

    def _begin_game(self):
        """StartScreen 의 Start 버튼 콜백."""
        if self.started:
            return
        self.started = True
        self.hud.show_gameplay()
        self.player._first_mouse = True
        self.player._capture_mouse()
        self.zombies.start_wave(1)

    def _toggle_pause(self):
        if not self.started:
            return
        if self.level_up_active:
            return
        self.paused = not self.paused
        if self.paused:
            self.settings_menu.show()
            props = WindowProperties()
            props.setCursorHidden(False)
            props.setMouseMode(WindowProperties.M_absolute)
            self.win.requestProperties(props)
        else:
            self.settings_menu.hide()
            self.player._first_mouse = True
            self.player._capture_mouse()

    def _on_mouse1(self):
        if self.started and not self.paused and not self.level_up_active:
            self.pistol.shoot()

    def _on_mouse3(self, active):
        if self.started and not self.paused and not self.level_up_active:
            self.player.set_ads(active)

    def _on_reload(self):
        if self.started and not self.paused and not self.level_up_active:
            self.pistol.reload()

    def _weapons_update_task(self, task):
        if not self.started or self.paused or self.level_up_active:
            return task.cont
        dt = _clock.getDt()
        self.pistol.update(dt)
        self.zombies.update(dt)
        return task.cont


def _assets_root():
    """프로젝트 루트의 assets/ 경로 — main.py 의 위치 기준으로 계산."""
    import pathlib
    return pathlib.Path(__file__).resolve().parent.parent / "assets"


def main():
    app = FPSGame()
    app.run()


if __name__ == "__main__":
    main()
