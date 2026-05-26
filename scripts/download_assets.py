"""PBR 에셋 일괄 다운로드 — 처음 클론 후 한 번 실행.

다운로드 대상:
  - ambientcg.com  Ground037 1K-JPG (Color/NormalGL/Roughness/AO)  → assets/textures/ground/
  - polyhaven.com  kloofendal_overcast_puresky 1K HDR              → assets/hdri/sky.hdr
  - kenney.nl      Blaster Kit (blaster-a.glb + colormap.png)      → assets/models/pistol/

세 사이트 모두 CC0 라이선스. 에셋 파일이 크고 자주 안 바뀌므로 git 에 안 올림
(.gitignore 에 assets/textures/, assets/hdri/, assets/models/ 등록되어 있음).

Idempotent — 이미 파일이 모두 있으면 다운로드를 건너뛴다. 부분 다운로드 후
중단된 경우엔 zip 임시 파일이 남을 수 있어 zip 추출 후 명시적으로 삭제.

실행:
    python scripts/download_assets.py
"""

from __future__ import annotations

import io
import os
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
GROUND_DIR = ROOT / "assets" / "textures" / "ground"
HDRI_DIR = ROOT / "assets" / "hdri"
PISTOL_DIR = ROOT / "assets" / "models" / "pistol"
ARM_DIR = ROOT / "assets" / "models" / "arms"

GROUND_ZIP_URL = "https://ambientcg.com/get?file=Ground037_1K-JPG.zip"
# kloofendal_overcast_puresky: 흐린 회색 하늘만 (지상 풍경 없음 — "puresky" 시리즈).
# 이전에 쓰던 cloudy_vondelpark 는 공원 360° 촬영본이라 나무/건물이 skybox 전체로
# 깔려 게임 분위기와 충돌했음. puresky 시리즈는 sky-only 라 게임용으로 적합.
HDRI_URL = "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/kloofendal_overcast_puresky_1k.hdr"

# Quaternius "9mm Pistol" (Beretta 9mm) — CC-BY 3.0, GLB 단일 파일.
# poly.pizza 호스팅. 본체 외에 Slide / Trigger / Hammer 가 별도 노드로 분리돼 있어
# 발사 시 슬라이드 후퇴 시각 효과가 실제 노드 모션으로 작동. Magazine 은 분리 안
# 됐지만 폴백으로 박스 mesh 추가하면 됨.
PISTOL_GLB_URL = "https://static.poly.pizza/e9192aa9-16b4-471d-a9c6-1823f8856b26.glb"
# CC-BY 3.0 attribution — assets/models/pistol/LICENSE.txt 로 같이 저장.
PISTOL_LICENSE_TEXT = (
    "9mm Pistol model by Quaternius — https://quaternius.com\n"
    "Sourced via poly.pizza (https://poly.pizza/m/BoZWhFdsj4).\n"
    "Licensed under Creative Commons Attribution 3.0 (CC-BY 3.0).\n"
    "https://creativecommons.org/licenses/by/3.0/\n"
)

# DJMaesen "First Person Arms" (Sketchfab, CC-BY 4.0) — 수동 다운로드 필요 (Sketchfab
# 다운로드는 로그인 요구 → curl 자동화 불가). assets/models/arms/scene.gltf + scene.bin +
# textures/ 가 이미 박혀 있으므로 이 함수는 존재 체크만 하고 누락 시 안내 메시지.
# URL: https://sketchfab.com/3d-models/first-person-arms-e3c42c05b22944e5839deb8e003f0987
ARM_LICENSE_TEXT = (
    "First Person Arms model by DJMaesen (@bumstrum)\n"
    "Sourced from Sketchfab "
    "(https://sketchfab.com/3d-models/first-person-arms-e3c42c05b22944e5839deb8e003f0987).\n"
    "Licensed under Creative Commons Attribution 4.0 (CC-BY 4.0).\n"
    "https://creativecommons.org/licenses/by/4.0/\n"
)

# ZIP 내부 파일 이름 → 우리 디렉토리에 저장할 깔끔한 이름
GROUND_FILE_MAP = {
    "Ground037_1K-JPG_Color.jpg": "ground_albedo.jpg",
    "Ground037_1K-JPG_NormalGL.jpg": "ground_normal.jpg",
    "Ground037_1K-JPG_Roughness.jpg": "ground_roughness.jpg",
    "Ground037_1K-JPG_AmbientOcclusion.jpg": "ground_ao.jpg",
}

# 일부 호스트는 빈 User-Agent 요청을 차단. 평범한 브라우저 UA 로 위장.
_REQ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    )
}


def _http_get(url: str) -> bytes:
    """단순 HTTP GET (redirect 따라감). 큰 파일은 chunk 로 받아 메모리 부담 완화."""
    req = urllib.request.Request(url, headers=_REQ_HEADERS)
    with urllib.request.urlopen(req) as resp:
        chunks: list[bytes] = []
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
            sys.stdout.write(".")
            sys.stdout.flush()
        sys.stdout.write("\n")
    return b"".join(chunks)


def _download_to(url: str, dest: Path) -> None:
    print(f"  GET {url}")
    data = _http_get(url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    print(f"  wrote {dest} ({len(data) / 1024:.0f} KB)")


def download_ground() -> None:
    GROUND_DIR.mkdir(parents=True, exist_ok=True)
    if all((GROUND_DIR / name).exists() for name in GROUND_FILE_MAP.values()):
        print("[ground] all PBR textures already present — skipping")
        return

    print("[ground] downloading Ground037 1K-JPG …")
    zip_bytes = _http_get(GROUND_ZIP_URL)
    print(f"[ground] downloaded {len(zip_bytes) / 1024:.0f} KB")

    extracted = 0
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for member in zf.namelist():
            basename = os.path.basename(member)
            mapped = GROUND_FILE_MAP.get(basename)
            if mapped is None:
                continue
            dst = GROUND_DIR / mapped
            with zf.open(member) as src_f, open(dst, "wb") as dst_f:
                shutil.copyfileobj(src_f, dst_f)
            print(f"[ground]  extracted {mapped}")
            extracted += 1

    if extracted != len(GROUND_FILE_MAP):
        print(
            f"[ground] WARNING: expected {len(GROUND_FILE_MAP)} files, extracted {extracted}",
            file=sys.stderr,
        )


def download_hdri() -> None:
    HDRI_DIR.mkdir(parents=True, exist_ok=True)
    sky_path = HDRI_DIR / "sky.hdr"
    if sky_path.exists():
        print("[hdri] sky.hdr already present — skipping")
        return
    print("[hdri] downloading sky HDR …")
    _download_to(HDRI_URL, sky_path)


def download_pistol() -> None:
    PISTOL_DIR.mkdir(parents=True, exist_ok=True)
    glb_path = PISTOL_DIR / "pistol.glb"
    lic_path = PISTOL_DIR / "LICENSE.txt"

    if glb_path.exists() and lic_path.exists():
        print("[pistol] pistol model + license already present — skipping")
        return

    print("[pistol] downloading Quaternius 9mm Pistol (CC-BY) …")
    _download_to(PISTOL_GLB_URL, glb_path)
    lic_path.write_text(PISTOL_LICENSE_TEXT, encoding="utf-8")
    print(f"[pistol]  wrote {lic_path}")


def download_arm() -> None:
    """DJMaesen FPS Arms — Sketchfab 다운로드는 로그인 필요해 자동화 불가.
    수동으로 assets/models/arms/ 에 scene.gltf + scene.bin + textures/ 를 두어야 함."""
    ARM_DIR.mkdir(parents=True, exist_ok=True)
    gltf_path = ARM_DIR / "scene.gltf"
    lic_path = ARM_DIR / "LICENSE.txt"

    if gltf_path.exists():
        print("[arm] scene.gltf already present — skipping")
        if not lic_path.exists():
            lic_path.write_text(ARM_LICENSE_TEXT, encoding="utf-8")
        return

    print(
        "[arm] WARNING: scene.gltf 가 없음. Sketchfab 에서 수동 다운로드 필요:\n"
        "      https://sketchfab.com/3d-models/first-person-arms-e3c42c05b22944e5839deb8e003f0987\n"
        "      로그인 → Download → glTF 선택 → 압축 풀어 assets/models/arms/ 에 저장.\n"
        "      파일 없으면 게임은 박스 폴백으로 자동 전환됨.",
        file=sys.stderr,
    )


def main() -> int:
    try:
        download_ground()
        download_hdri()
        download_pistol()
        download_arm()
    except urllib.error.URLError as e:
        print(f"\nERROR: download failed — {e}", file=sys.stderr)
        return 1
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
