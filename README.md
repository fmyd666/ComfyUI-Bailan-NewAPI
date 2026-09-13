# ComfyUI-Bailan-NewAPI

摆烂 New-API 图片/视频节点。地址默认 `https://newapi.bailan.store`。

## 安装

```text
cd ComfyUI\custom_nodes
rmdir /s /q ComfyUI-Bailan-NewAPI
git clone https://github.com/fmyd666/ComfyUI-Bailan-NewAPI.git
```

完全关掉 ComfyUI 再打开。搜索 **摆烂** 或 **Bailan**，不要只搜 `bai`。

## 节点

1. **摆烂 New 图/视频**
   - Key、模式图片/视频、模型、分辨率、时长/数量、提示词、负提示词
   - 可选 `image`：图模式=参考改图；视频模式=首帧/参考图
   - 输出：预览图、视频路径、日志
2. **摆烂 保存视频**
   - 把上面的视频路径连进来，另存一份到 `output/bailan_newapi/`
3. **摆烂 刷新模型**
   - 用 Key 调 `GET /v1/models`，写入本地缓存，日志里列出 seedream/seedance

视频 480p/720p/1080p 会自动换模型名。Key 用 New 的令牌。
