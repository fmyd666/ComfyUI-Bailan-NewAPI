import io
import json
import os
import time
import urllib.error
import urllib.request

import numpy as np
import torch
from PIL import Image

BASE_DEFAULT = "https://newapi.bailan.store"
IMAGE_MODEL = "doubao-seedream-5-0-260128"
VIDEO_MODEL = "doubao-seedance-2-0-260128"
VIDEO_MODELS = {
    "480p": "doubao-seedance-2-0-260128-480p",
    "720p": "doubao-seedance-2-0-260128",
    "1080p": "doubao-seedance-2-0-260128-1080p",
}
VIDEO_PRICE = {"480p": 1.0, "720p": 2.0, "1080p": 6.2}


def _mask_key(key):
    key = (key or "").strip()
    if len(key) <= 8:
        return "***"
    return key[:4] + "***" + key[-4:]


def _http_json(url, method="GET", headers=None, data=None, timeout=180):
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if not raw:
                return {}, resp.status
            return json.loads(raw.decode("utf-8", errors="replace")), resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"error": raw[:800]}
        raise RuntimeError(json.dumps(parsed, ensure_ascii=False)[:800]) from e


def _download_bytes(url, timeout=180):
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _image_to_tensor(img):
    img = img.convert("RGB")
    arr = np.array(img).astype(np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...]


def _blank(h=64, w=64):
    return torch.zeros((1, h, w, 3), dtype=torch.float32)


def _pick_video_model(model, resolution):
    model = (model or "").strip() or VIDEO_MODEL
    resolution = (resolution or "720p").lower()
    if model.endswith("-480p") or model.endswith("-1080p"):
        return model, ("480p" if model.endswith("-480p") else "1080p")
    return VIDEO_MODELS.get(resolution, VIDEO_MODEL), resolution if resolution in VIDEO_MODELS else "720p"


def _task_id(payload):
    if not isinstance(payload, dict):
        return ""
    for k in ("id", "task_id", "taskId"):
        if payload.get(k):
            return str(payload[k])
    data = payload.get("data") or {}
    if isinstance(data, dict):
        for k in ("id", "task_id", "taskId"):
            if data.get(k):
                return str(data[k])
    return ""


def _media_url(payload):
    if not isinstance(payload, dict):
        return ""
    for k in ("url", "video_url", "image_url"):
        if payload.get(k):
            return str(payload[k])
    data = payload.get("data")
    if isinstance(data, list) and data:
        item = data[0] if isinstance(data[0], dict) else {}
        return str(item.get("url") or item.get("b64_json") or "")
    if isinstance(data, dict):
        for k in ("url", "video_url", "output", "file_url"):
            if data.get(k):
                return str(data[k])
        out = data.get("output") or {}
        if isinstance(out, dict):
            return str(out.get("url") or "")
    return ""


class BailanNewAPI:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_key": ("STRING", {"default": "", "multiline": False}),
                "mode": (["图片", "视频"],),
                "prompt": ("STRING", {"default": "", "multiline": True}),
                "negative_prompt": ("STRING", {"default": "", "multiline": True}),
                "model": ("STRING", {"default": IMAGE_MODEL}),
                "resolution": (["480p", "720p", "1080p", "1K", "2K", "3K"], {"default": "720p"}),
                "duration": ("INT", {"default": 4, "min": 4, "max": 15, "step": 1}),
                "count": ("INT", {"default": 1, "min": 1, "max": 4, "step": 1}),
            },
            "optional": {
                "base_url": ("STRING", {"default": BASE_DEFAULT}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "log")
    FUNCTION = "run"
    CATEGORY = "摆烂/Bailan"

    def run(self, api_key, mode, prompt, negative_prompt, model, resolution, duration, count, base_url=BASE_DEFAULT):
        logs = []
        key = (api_key or "").strip()
        base = (base_url or BASE_DEFAULT).rstrip("/")
        prompt = (prompt or "").strip()
        if not key:
            return (_blank(), "缺 Key：填 New 后台令牌")
        if not prompt:
            return (_blank(), "缺提示词")
        headers = {
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
        }
        logs.append("base=" + base)
        logs.append("key=" + _mask_key(key))
        try:
            if mode == "视频":
                use_model, res = _pick_video_model(model if "seedance" in (model or "").lower() else VIDEO_MODEL, resolution if resolution.endswith("p") else "720p")
                price = VIDEO_PRICE.get(res, 2.0)
                logs.append("mode=视频 model=%s seconds=%s est=%s元*分组" % (use_model, duration, price * duration))
                payload = {
                    "model": use_model,
                    "prompt": prompt,
                    "seconds": str(int(duration)),
                    "size": res,
                }
                if negative_prompt:
                    payload["negative_prompt"] = negative_prompt
                created, _ = _http_json(base + "/v1/video/generations", "POST", headers, payload, 180)
                tid = _task_id(created)
                url = _media_url(created)
                logs.append("submit=" + json.dumps({k: created.get(k) for k in list(created)[:8]}, ensure_ascii=False)[:300])
                status = (created.get("status") if isinstance(created, dict) else "") or ""
                deadline = time.time() + 420
                while not url and time.time() < deadline:
                    time.sleep(5)
                    paths = []
                    if tid:
                        paths.extend([
                            base + "/v1/video/generations/" + tid,
                            base + "/v1/videos/" + tid,
                        ])
                    for p in paths:
                        try:
                            info, _ = _http_json(p, "GET", headers, None, 60)
                            status = str(info.get("status") or status)
                            url = _media_url(info) or url
                            if url or status.lower() in ("failed", "error"):
                                break
                        except Exception as e:
                            logs.append("poll_err=" + str(e)[:200])
                    if url or status.lower() in ("failed", "error"):
                        break
                if not url:
                    return (_blank(), "\n".join(logs + ["视频超时或失败 status=" + str(status)]))
                raw = _download_bytes(url)
                out_dir = os.path.join("output", "bailan_newapi")
                os.makedirs(out_dir, exist_ok=True)
                path = os.path.join(out_dir, "video_%s.mp4" % int(time.time()))
                with open(path, "wb") as f:
                    f.write(raw)
                logs.append("saved=" + path)
                return (_blank(128, 128), "\n".join(logs))
            use_model = (model or "").strip() or IMAGE_MODEL
            size = resolution if resolution in ("1K", "2K", "3K") else "2K"
            logs.append("mode=图片 model=%s size=%s n=%s" % (use_model, size, count))
            payload = {
                "model": use_model,
                "prompt": prompt,
                "size": size,
                "n": int(count),
                "response_format": "url",
            }
            if negative_prompt:
                payload["negative_prompt"] = negative_prompt
            created, _ = _http_json(base + "/v1/images/generations", "POST", headers, payload, 180)
            url = _media_url(created)
            if not url:
                return (_blank(), "\n".join(logs + ["图片没返回 url: " + json.dumps(created, ensure_ascii=False)[:400]]))
            raw = _download_bytes(url)
            img = Image.open(io.BytesIO(raw))
            logs.append("ok size=%sx%s" % img.size)
            return (_image_to_tensor(img), "\n".join(logs))
        except Exception as e:
            logs.append("error=" + str(e)[:500])
            return (_blank(), "\n".join(logs))


NODE_CLASS_MAPPINGS = {
    "BailanNewAPI": BailanNewAPI,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "BailanNewAPI": "摆烂 New 图/视频",
}
