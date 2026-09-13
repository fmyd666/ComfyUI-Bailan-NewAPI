import base64
import io
import json
import os
import shutil
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
CACHE_PATH = os.path.join(os.path.dirname(__file__), "models_cache.json")


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


def _tensor_to_data_url(image):
    if image is None:
        return ""
    arr = image
    if hasattr(arr, "cpu"):
        arr = arr.cpu().numpy()
    if arr.ndim == 4:
        arr = arr[0]
    arr = (np.clip(arr, 0, 1) * 255).astype(np.uint8)
    im = Image.fromarray(arr)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


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
        return str(item.get("url") or "")
    if isinstance(data, dict):
        for k in ("url", "video_url", "output", "file_url"):
            if data.get(k):
                return str(data[k])
        out = data.get("output") or {}
        if isinstance(out, dict):
            return str(out.get("url") or "")
    return ""


def _out_dir():
    path = os.path.join("output", "bailan_newapi")
    os.makedirs(path, exist_ok=True)
    return path


def _fetch_models(base, key):
    headers = {"Authorization": "Bearer " + key}
    data, _ = _http_json(base.rstrip("/") + "/v1/models", "GET", headers, None, 30)
    items = data.get("data") if isinstance(data, dict) else data
    names = []
    if isinstance(items, list):
        for it in items:
            if isinstance(it, dict) and it.get("id"):
                names.append(str(it["id"]))
            elif isinstance(it, str):
                names.append(it)
    prefer = [n for n in names if "seedream" in n.lower() or "seedance" in n.lower()]
    chosen = prefer or names
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(chosen, f, ensure_ascii=False, indent=2)
    return chosen


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
                "image": ("IMAGE",),
                "base_url": ("STRING", {"default": BASE_DEFAULT}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("image", "video_path", "log")
    FUNCTION = "run"
    CATEGORY = "摆烂/Bailan"

    def run(self, api_key, mode, prompt, negative_prompt, model, resolution, duration, count, image=None, base_url=BASE_DEFAULT):
        logs = []
        key = (api_key or "").strip()
        base = (base_url or BASE_DEFAULT).rstrip("/")
        prompt = (prompt or "").strip()
        if not key:
            return (_blank(), "", "缺 Key：填 New 后台令牌")
        if not prompt:
            return (_blank(), "", "缺提示词")
        headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
        ref = _tensor_to_data_url(image) if image is not None else ""
        logs.append("base=" + base)
        logs.append("key=" + _mask_key(key))
        if ref:
            logs.append("ref_image=yes")
        try:
            if mode == "视频":
                use_model, res = _pick_video_model(model if "seedance" in (model or "").lower() else VIDEO_MODEL, resolution if str(resolution).endswith("p") else "720p")
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
                if ref:
                    payload["images"] = [ref]
                    payload["input_reference"] = {"image_url": ref}
                created, _ = _http_json(base + "/v1/video/generations", "POST", headers, payload, 180)
                tid = _task_id(created)
                url = _media_url(created)
                logs.append("submit_id=" + (tid or "none"))
                status = str((created.get("status") if isinstance(created, dict) else "") or "")
                deadline = time.time() + 420
                while not url and time.time() < deadline:
                    time.sleep(5)
                    if not tid:
                        break
                    for p in (base + "/v1/video/generations/" + tid, base + "/v1/videos/" + tid):
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
                    return (_blank(), "", "\n".join(logs + ["视频超时或失败 status=" + status]))
                raw = _download_bytes(url)
                path = os.path.join(_out_dir(), "video_%s.mp4" % int(time.time()))
                with open(path, "wb") as f:
                    f.write(raw)
                logs.append("saved=" + path)
                return (_blank(128, 128), path, "\n".join(logs))
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
            if ref:
                payload["image"] = ref
            created, _ = _http_json(base + "/v1/images/generations", "POST", headers, payload, 180)
            url = _media_url(created)
            if not url:
                return (_blank(), "", "\n".join(logs + ["图片没返回 url: " + json.dumps(created, ensure_ascii=False)[:400]]))
            raw = _download_bytes(url)
            img = Image.open(io.BytesIO(raw))
            logs.append("ok size=%sx%s" % img.size)
            return (_image_to_tensor(img), "", "\n".join(logs))
        except Exception as e:
            logs.append("error=" + str(e)[:500])
            return (_blank(), "", "\n".join(logs))


class BailanSaveVideo:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_path": ("STRING", {"default": "", "multiline": False}),
                "filename_prefix": ("STRING", {"default": "bailan_video"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("saved_path", "log")
    FUNCTION = "run"
    CATEGORY = "摆烂/Bailan"
    OUTPUT_NODE = True

    def run(self, video_path, filename_prefix):
        src = (video_path or "").strip()
        if not src:
            return ("", "缺 video_path，把「摆烂 New 图/视频」的 video_path 连过来")
        if src.startswith("http://") or src.startswith("https://"):
            raw = _download_bytes(src)
            dest = os.path.join(_out_dir(), "%s_%s.mp4" % (filename_prefix or "bailan_video", int(time.time())))
            with open(dest, "wb") as f:
                f.write(raw)
            return (dest, "downloaded " + dest)
        if not os.path.isfile(src):
            return ("", "找不到文件: " + src)
        dest = os.path.join(_out_dir(), "%s_%s%s" % (filename_prefix or "bailan_video", int(time.time()), os.path.splitext(src)[1] or ".mp4"))
        shutil.copy2(src, dest)
        return (dest, "copied " + dest)


class BailanRefreshModels:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "api_key": ("STRING", {"default": "", "multiline": False}),
            },
            "optional": {
                "base_url": ("STRING", {"default": BASE_DEFAULT}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("models",)
    FUNCTION = "run"
    CATEGORY = "摆烂/Bailan"
    OUTPUT_NODE = True

    def run(self, api_key, base_url=BASE_DEFAULT):
        key = (api_key or "").strip()
        if not key:
            return ("缺 Key",)
        try:
            names = _fetch_models(base_url or BASE_DEFAULT, key)
            text = "\n".join(names) if names else "上游没返回模型"
            return (text,)
        except Exception as e:
            fallback = [IMAGE_MODEL, VIDEO_MODEL, VIDEO_MODELS["480p"], VIDEO_MODELS["1080p"]]
            return ("拉取失败: %s\n回退:\n%s" % (str(e)[:200], "\n".join(fallback)),)


NODE_CLASS_MAPPINGS = {
    "BailanNewAPI": BailanNewAPI,
    "BailanSaveVideo": BailanSaveVideo,
    "BailanRefreshModels": BailanRefreshModels,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "BailanNewAPI": "摆烂 New 图/视频",
    "BailanSaveVideo": "摆烂 保存视频",
    "BailanRefreshModels": "摆烂 刷新模型",
}
