# VideoExplore

Samba 上の大量動画を検索可能にする動画セマンティック検索システム。
設計の全体像は [docs/design.md](docs/design.md) を参照。

## 実装状況

- ✅ **テキスト検索 → 動画リスト可視化 → 即再生**(P1 + P3 一部)
  - スキャン → ffprobe メタ取得 → サムネイル生成
  - SigLIP2 ゼロショット自動タグ付け(GPU)
  - **GLM-5.3-Flash(ローカル vLLM)による映像説明文・タグ生成**(1動画約10秒)
  - 検索対象: タグ(日英エイリアス)+ ファイル名 + **GLM 日本語説明文**
  - 結果をサムネイルグリッドで可視化、クリックで即再生(Range ストリーミング)
- ⬜ シーン分割・フレーム/車両埋め込み・画像検索(P2)
- ⬜ pgroonga 導入・セマンティックベクトル検索(P3 本体)

## クイックスタート

```bash
cp .env.example .env

# 動作確認用サンプル(任意)
bash scripts/fetch_sample_videos.sh

docker compose up -d --build

# スキャン(UI の「スキャン」ボタンでも可)
curl -X POST http://localhost:8010/api/admin/scan
```

- **Web UI: http://localhost:3001** — サーバー自身で開く場合。別PCからは `http://<サーバーIP>:3001`
  (UI と API は nginx が同一オリジンで中継するため、別PCからでも追加設定なしで動作します)
- API 直叩き(開発用): http://localhost:8010/docs

### ポートについて(このマシン固有)

| ポート | 用途 | 備考 |
|---|---|---|
| 3001 | **Web UI(nginx ゲートウェイ)** | ブラウザはここだけ使う。3000 は既存 Open WebUI と衝突 |
| 8010 | API 直アクセス用 | 8000 は GLM vLLM(NVFP4/TP2)用に予約 |
| 8888 | GLM-5.3-Flash vLLM(既存) | VideoExplore から利用 |

### Samba の動画を対象にする

`VIDEO_HOST_DIR`(既定 `./data/videos`)に読み取り専用マウントする:

```bash
sudo mount -t cifs //NASのIP/共有名 ./data/videos \
  -o vers=3.1.1,ro,iocharset=utf8,credentials=/etc/videoexplore/smb.cred
```

マウント後にスキャンすれば NAS 上の動画が順次解析される。

## パイプライン(動画の状態遷移)

```
discovered → processing(メタ+サムネ) → ingested → tagging(SigLIP2) → caption(GLM-5.3) → ready
```

`ready` 以前でも一覧・ファイル名検索・再生は可能。タグ/説明文は解析後に付与。
失敗時は `error`。`POST /api/admin/reanalyze` で全動画の再解析が可能。

## 主要 API

| メソッド | パス | 内容 |
|---|---|---|
| GET | `/api/search?q=&page=` | テキスト検索(GLM説明文+タグ+ファイル名) |
| GET | `/api/videos?page=` | ライブラリ一覧 |
| GET | `/api/videos/{id}` | 動画詳細(GLM説明文を含む) |
| GET | `/api/videos/{id}/thumb` | サムネイル |
| GET | `/api/videos/{id}/stream` | 動画ストリーミング(Range 対応) |
| GET | `/api/tags` | タグ語彙と件数 |
| POST | `/api/admin/scan` | フォルダ再スキャン |
| POST | `/api/admin/reanalyze` | 全動画のタグ/キャプション再生成 |
| GET | `/api/admin/stats` | 解析進捗統計 |

## 設定(.env)

| 変数 | 既定 | 説明 |
|---|---|---|
| `VIDEO_HOST_DIR` | `./data/videos` | 動画ルート(SMB マウントポイント) |
| `CACHE_HOST_DIR` | `./cache` | サムネ・キーフレーム・HFモデルキャッシュ |
| `EMBED_MODEL` | `google/siglip2-base-patch16-256` | タグ付けモデル |
| `TAG_THRESHOLD` | `0.05` | タグ採用しきい値(softmax確率) |
| `FRAMES_PER_VIDEO` | `12` | 動画あたり解析フレーム数 |
| `GLM_ENABLED` | `true` | GLM キャプションの有効化 |
| `GLM_API_URL` | `http://host.docker.internal:8888/v1` | vLLM OpenAI互換API |
| `GLM_MODEL` | `GLM-5.3-Flash-EXL3` | モデルID(/v1/models の id) |
| `CAPTION_FRAMES` | `3` | キャプションに使うキーフレーム数 |

## トラブルシューティング

- GPU が見えるか: `docker compose exec worker-gpu nvidia-smi`
- GLM サーバ確認: `curl http://localhost:8888/v1/models`
- タグが付かない → `docker compose logs worker-gpu` / `POST /api/admin/reanalyze`
- GLM キャプション失敗 → GLM サーバ起動確認と `reanalyze` で再実行
