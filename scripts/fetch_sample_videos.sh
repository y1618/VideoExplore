#!/usr/bin/env bash
# 動作確認用のサンプル動画(CCライセンス)をダウンロードする
# 使い方: bash scripts/fetch_sample_videos.sh [出力先: data/videos]
set -u

DEST="${1:-data/videos}"
mkdir -p "$DEST"

declare -A URLS=(
  ["sample_bunny.mp4"]="https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/720/Big_Buck_Bunny_720_10s_1MB.mp4"
  ["sample_sintel.mp4"]="https://test-videos.co.uk/vids/sintel/mp4/h264/720/Sintel_720_10s_1MB.mp4"
  ["sample_tears.mp4"]="https://test-videos.co.uk/vids/tearsofsteel/mp4/h264/720/Tears_of_Steel_720_10s_1MB.mp4"
  ["sample_jellyfish.mp4"]="https://test-videos.co.uk/vids/jellyfish/mp4/h264/720/Jellyfish_720_10s_1MB.mp4"
)

ok=0
for name in "${!URLS[@]}"; do
  out="$DEST/$name"
  if [ -s "$out" ]; then echo "skip  $name"; ok=$((ok+1)); continue; fi
  if curl -fL --retry 2 -m 120 -o "$out" "${URLS[$name]}"; then
    echo "OK    $name"; ok=$((ok+1))
  else
    echo "FAIL  $name"; rm -f "$out"
  fi
done

echo "----"
ls -la "$DEST"
if [ "$ok" -eq 0 ]; then
  echo "ダウンロードに失敗しました。data/videos に任意の mp4 を配置してください。"
fi
