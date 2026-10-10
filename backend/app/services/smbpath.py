r"""相対パスを SMB UNC フルパスへ変換する。

data/smb.mounts (scripts/mount_samba.sh と同じ書式) を解析し、
先頭要素がマウント時のサブディレクトリと一致する動画パスを
  //NAS_HOST/share/sub/foo.mp4
  → \\NAS_HOST\share\sub\foo.mp4
の形式に変換する。マウント一覧が無い/一致しない場合は None。
"""
import os
from functools import lru_cache

from app.config import settings


@lru_cache(maxsize=1)
def _mounts() -> dict[str, str]:
    path = settings.smb_mounts_file
    if not path or not os.path.isfile(path):
        return {}
    mapping: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if not parts or parts[0].startswith("#"):
                continue
            if len(parts) == 1:
                src = parts[0]
                sub = os.path.basename(src.rstrip("/"))
            else:
                sub, src = parts[0], parts[1]
            mapping[sub] = src.rstrip("/")
    return mapping


def to_unc(rel_path: str) -> str | None:
    rel = rel_path.replace("\\", "/").lstrip("/")
    if "/" not in rel:
        return None
    sub, rest = rel.split("/", 1)
    src = _mounts().get(sub)
    if not src:
        return None
    unc = src.replace("/", "\\")
    if not unc.startswith("\\\\"):
        unc = "\\\\" + unc.lstrip("\\")
    return unc + "\\" + rest.replace("/", "\\")
