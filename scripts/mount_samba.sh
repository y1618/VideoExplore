#!/bin/bash
# DS423 (Synology) の SMB 共有を data/videos に読み取り専用マウントする
# 使い方: sudo bash scripts/mount_samba.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGIN="$REPO_DIR/data/smb.cred"
MOUNT_DIR="$REPO_DIR/data/videos"
# \\Ds423\DVD9\net_downloads  (Ds423 = 192.168.50.250, 共有名は大文字 DVD9)
SRC="//192.168.50.250/DVD9/net_downloads"

mkdir -p "$MOUNT_DIR"

if mountpoint -q "$MOUNT_DIR"; then
  echo "already mounted: $MOUNT_DIR"
  df -h "$MOUNT_DIR"
  exit 0
fi

LOG=/tmp/mount_samba.log
{
  echo "=== $(date) ==="
  echo "SRC=$SRC MOUNT_DIR=$MOUNT_DIR LOGIN=$LOGIN"
  mount -t cifs "$SRC" "$MOUNT_DIR" \
    -o "credentials=$LOGIN,vers=3.1.1,ro,iocharset=utf8,uid=$(id -u),gid=$(id -g),nobrl,_netdev" \
    -v
} >"$LOG" 2>&1

echo "mounted: $SRC -> $MOUNT_DIR"
df -h "$MOUNT_DIR"

# 再起動後も自動マウントするには /etc/fstab に次を追記 (sudo ./fstab は不可のため手動):
# //192.168.50.250/DVD9/net_downloads  $MOUNT_DIR  cifs  credentials=$LOGIN,vers=3.1.1,ro,iocharset=utf8,uid=$(id -u),gid=$(id -g),nobrl,_netdev,noauto,x-systemd.automount  0 0
