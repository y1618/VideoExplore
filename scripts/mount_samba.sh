#!/bin/bash
# 複数の SMB 共有を data/videos/<サブディレクトリ> に読み取り専用マウントする
# 使い方: sudo bash scripts/mount_samba.sh
# マウント一覧: data/smb.mounts (1行: [サブディレクトリ] <//server/share[/path]>)
#   - サブディレクトリ省略時は UNC パスの末尾要素を使う
#   - 先頭が # の行はコメント
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGIN="$REPO_DIR/data/smb.cred"
BASE="$REPO_DIR/data/videos"
LIST="$REPO_DIR/data/smb.mounts"

[ -f "$LOGIN" ] || { echo "credentials not found: $LOGIN"; exit 1; }
[ -f "$LIST" ] || { echo "mount list not found: $LIST"; exit 1; }

mkdir -p "$BASE"

# 旧構成(data/videos 自体がマウントポイント)なら一旦アンマウントしてサブディレクトリ方式へ移行
if mountpoint -q "$BASE"; then
  echo "unmount old-style mount: $BASE"
  umount "$BASE"
fi

OPTS="credentials=$LOGIN,vers=3.1.1,ro,iocharset=utf8,uid=$(id -u),gid=$(id -g),nobrl"

FSTAB_LINES=""
while read -r sub src || [ -n "${sub:-}" ]; do
  case "${sub:-}" in ""|\#*) continue;; esac
  if [ -z "${src:-}" ]; then
    src="$sub"
    sub="$(basename "$src")"
  fi
  tgt="$BASE/$sub"
  mkdir -p "$tgt"
  if mountpoint -q "$tgt"; then
    echo "already mounted: $tgt"
  else
    echo "mount: $src -> $tgt"
    mount -t cifs "$src" "$tgt" -o "$OPTS"
  fi
  FSTAB_LINES+="$src $tgt cifs ${OPTS},_netdev,noauto,x-systemd.automount 0 0"$'\n'
done < "$LIST"

echo
df -h "$BASE" | grep -E "cifs|Filesystem" || true

echo
echo "--- /etc/fstab 用行(起動時自動マウントしたい場合) ---"
echo "$FSTAB_LINES"
