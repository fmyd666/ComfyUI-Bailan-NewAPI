# ComfyUI-Bailan-NewAPI

摆烂 New-API 图片/视频节点。地址写死 `https://newapi.bailan.store`，填 New 的 Key 即可。

## 安装

便携版：

```text
cd ComfyUI\custom_nodes
git clone https://github.com/fmyd666/ComfyUI-Bailan-NewAPI.git
```

重启 ComfyUI。右键搜索：`摆烂` 或 `Bailan`。

## 节点

- **摆烂 New 配置**：只填 Key（可选）
- **摆烂 生图**：Seedream，接口 `/v1/images/generations`
- **摆烂 生视频**：Seedance，接口 `/v1/video/generations`

## 填法

| 项 | 值 |
|---|---|
| 地址 | 默认 `https://newapi.bailan.store`，不要改 |
| Key | New 后台开的令牌，不要用 Sub2API |
| 生图模型 | `doubao-seedream-5-0-260128` |
| 视频 720P | `doubao-seedance-2-0-260128` |
| 视频 480P | 分辨率选 480p，插件会自动换模型名 |
| 视频 1080P | 分辨率选 1080p |
| 时长 | 4–15 秒，费用 = 标价 × 秒 × 分组 |

负提示词会发出去；Seedream 上游可能忽略。日志里 Key 会打码。
