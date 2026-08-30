"""SigLIP2 を使ったゼロショットタグ推定(画像 x テキストプロンプト)。"""

from __future__ import annotations

import threading
from typing import Sequence

import numpy as np

_lock = threading.Lock()
_state: dict = {}


def _load() -> dict:
    import torch
    from transformers import AutoProcessor, AutoTokenizer, SiglipModel

    from app.config import settings

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    # SigLIP2 は SigLIP と同アーキテクチャのため SiglipModel でロードする
    try:
        model = SiglipModel.from_pretrained(settings.embed_model, dtype=dtype)
    except TypeError:  # transformers 4.x は torch_dtype
        model = SiglipModel.from_pretrained(settings.embed_model, torch_dtype=dtype)
    model.to(device)
    model.eval()
    processor = AutoProcessor.from_pretrained(settings.embed_model)
    tokenizer = AutoTokenizer.from_pretrained(settings.embed_model)

    _state.update(
        model=model, processor=processor, tokenizer=tokenizer, device=device, torch_dtype=dtype
    )
    print(f"[vision] model loaded: {settings.embed_model} on {device}")
    return _state


def get_state() -> dict:
    with _lock:
        if not _state:
            return _load()
        return _state


def zero_shot_probs(
    frame_paths: Sequence[str], prompts: Sequence[str]
) -> np.ndarray:
    """(フレーム数 x プロンプト数) の sigmoid 確率行列を返す。"""
    import torch
    import torch.nn.functional as F
    from PIL import Image

    if not frame_paths or not prompts:
        return np.zeros((len(frame_paths), len(prompts)), dtype=np.float32)

    st = get_state()
    images = [Image.open(p).convert("RGB") for p in frame_paths]

    with torch.no_grad():
        image_inputs = st["processor"](images=images, return_tensors="pt").to(st["device"])
        image_feats = st["model"].get_image_features(**image_inputs)

        text_inputs = st["tokenizer"](
            text=list(prompts),
            padding="longest",
            truncation=True,
            max_length=64,
            return_tensors="pt",
        ).to(st["device"])
        text_feats = st["model"].get_text_features(**text_inputs)

    image_feats = F.normalize(image_feats.float(), dim=-1)
    text_feats = F.normalize(text_feats.float(), dim=-1)

    # 学習済み logit_scale(温度)を使用。無ければ 100 を仮定
    logit_scale = getattr(st["model"], "logit_scale", None)
    scale = float(logit_scale.exp().item()) if logit_scale is not None else 100.0
    logits = image_feats @ text_feats.T * scale
    # タグ軸で softmax(標準的なゼロショット分類と同じ扱い)
    probs = torch.softmax(logits, dim=1)
    return probs.cpu().numpy()
