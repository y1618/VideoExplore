# VideoExplore

Samba 上の大量動画を検索可能にする動画セマンティック検索システム。
設計の全体像は [docs/design.md](docs/design.md) を参照。

## 実装状況

- ✅ **テキスト検索 → 動画リスト可視化 → 即再生**(P1 + P3 一部)
  - スキャン → ffprobe メタ取得 → サムネイル生成
  - SigLIP2 ゼロショット自動タグ付け(GPU)
  - **VLM(ローカル vLLM: DeepSeek-V4 Flash Vision Exp)による映像説明文・タグ生成**(1動画約10秒)
  - 検索対象: タグ(日英エイリアス)+ ファイル名 + **VLM 日本語説明文**
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
| 8010 | API 直アクセス用 | 8000 は vLLM(NVFP4/TP2)用に予約 |
| 8888 | VLM vLLM(既存) | VideoExplore から利用 |

### Samba の動画を対象にする(複数マウント対応)

`VIDEO_HOST_DIR`(既定 `./data/videos`)を親ディレクトリにし、SMB 共有をその**サブディレクトリ**に読み取り専用マウントします。複数の共有/フォルダを同時に取り込めます(スキャナが再帰走査します)。

1. 認証ファイル `data/smb.cred`(gitignore 対象)を用意:

   ```
   username=<SMBユーザー>
   password=<SMBパスワード>
   ```

2. マウント一覧 `data/smb.mounts` に1行ずつ記載(サブディレクトリ省略時はパス末尾要素):

   ```
   //<サーバー>/<共有>/<パス>
   movie //<サーバー>/<共有>
   ```

3. マウント実行(root 必要。既に `data/videos` 自体がマウントされていた場合は自動で解除して移行):

   ```bash
   sudo bash scripts/mount_samba.sh
   ```

4. マウント追加/変更後は**コンテナを再作成**してからスキャン(バインドマウントは起動時に確定されるため):

   ```bash
   docker compose up -d --force-recreate api worker-cpu worker-gpu
   curl -X POST http://localhost:8010/api/admin/scan
   ```

マウント構成を変えてパスが変わると同一動画が別パスで重複登録されるため、その場合は DB を一度クリアする(下記)か手動で削除してください:

```bash
docker compose exec db psql -U videoexplore -d videoexplore -c \
  "TRUNCATE video_tags, scenes, videos, taxonomy RESTART IDENTITY CASCADE;"
```

## パイプライン(動画の状態遷移)

```
discovered → processing(メタ+サムネ) → ingested → tagging(SigLIP2) → caption(VLM) → ready
```

`ready` 以前でも一覧・ファイル名検索・再生は可能。タグ/説明文は解析後に付与。
失敗時は `error`。`POST /api/admin/reanalyze` で全動画の再解析が可能。

## 主要 API

| メソッド | パス | 内容 |
|---|---|---|
| GET | `/api/search?q=&page=` | テキスト検索(VLM説明文+タグ+ファイル名) |
| GET | `/api/videos?page=` | ライブラリ一覧 |
| GET | `/api/videos/{id}` | 動画詳細(VLM説明文を含む) |
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
| `VLM_ENABLED` | `true` | VLM キャプションの有効化 |
| `VLM_API_URL` | `http://host.docker.internal:8888/v1` | vLLM OpenAI互換API |
| `VLM_MODEL` | `deepseek-v4-flash-vision-exp` | モデルID(/v1/models の id) |
| `CAPTION_FRAMES` | `3` | キャプションに使うキーフレーム数 |

## トラブルシューティング

- GPU が見えるか: `docker compose exec worker-gpu nvidia-smi`
- VLM サーバ確認: `curl http://localhost:8888/v1/models`
- タグが付かない → `docker compose logs worker-gpu` / `POST /api/admin/reanalyze`
- VLM キャプション失敗 → VLM サーバ起動確認と `reanalyze` で再実行
