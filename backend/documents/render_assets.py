"""أصول مضمنة في PDF؛ لا طلبات شبكة ولا مسارات مكشوفة لمحرك الرسم."""

import base64
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def render_assets() -> dict[str, str]:
    logo = (Path(__file__).resolve().parent / "assets" / "moe-logo.png").read_bytes()
    return {
        "ministry_logo_data_uri": "data:image/png;base64,"
        + base64.b64encode(logo).decode("ascii")
    }
