# javdb-ss 🎬

一个 Telegram 搜番机器人：发番号，返回**遮罩封面**、**中文简介**、**磁力 Top3**。

```
你：/s MIDA-497

Bot：[🔞 遮罩封面，点击查看]
     🎬 MIDA-497
     比基尼亲密接触！口优春药男士美学沙龙石川澪…
     ⭐ 4.34 | 📅 2026-02-04 | ⏱️ 170分钟
     👩 石川澪

     📝 标题翻译
     …

     🏷️ 单体作品 · 接吻 · 女上位 · 美容院
     🏢 MOODYZ

     🧲 磁力 Top3（中字优先）
     1️⃣ MIDA-497-C.torrent [中字·高清]
     📦 7.3 GB
     magnet:?xt=urn:btih:…  ← 点击复制
```

## ✨ 功能

| 功能 | 说明 |
|---|---|
| 🔍 `/s <番号>` | 精确搜番，私聊 / 群组都可用 |
| 📷 **以图搜番** | **私聊**直接发图识别（群组里不可用，静默忽略） |
| 🖼️ 遮罩封面 | 封面以 Telegram spoiler 形式发送，点一下才看 |
| 🌐 中文翻译 | 标题/简介自动 Google 翻译为中文 |
| 🧲 磁力 Top3 | **中文字幕优先**，同组按体积排序，附名称/大小/标记，一键复制 |
| ⚡ 内联搜索 | 任意聊天输入 `@你的Bot 番号` 即可搜 |
| 🛡️ 限流 + 缓存 | 番号搜索 3 秒冷却，以图搜番 10 秒冷却，结果缓存 1 小时 |

## 🧰 依赖

- Python 3.10+
- [javdb-cli](https://github.com/FlanChanXwO/javdb-cli) —— 搜索/详情/磁力/封面解密全走它（App API，**无需登录**）
- Telegram Bot Token（[@BotFather](https://t.me/BotFather) 创建）

## 🚀 搭建

```bash
git clone https://github.com/bbemby/javdb-ss.git
cd javdb-ss
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# 1. 装好 javdb-cli 并放到 ~/bin/javdb（或设 JAVDB_BIN 环境变量）
# 2. 设置 token 后启动
export BOT_TOKEN="123456:ABC-DEF..."
./venv/bin/python bot.py
```

### 可调参数（环境变量）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `BOT_TOKEN` | — | **必填**，Telegram Bot Token |
| `JAVDB_BIN` | `~/bin/javdb` | javdb-cli 路径 |
| `MAGNET_COUNT` | `3` | 展示的磁力数量 |
| `RATE_LIMIT_SECONDS` | `3` | 番号搜索单用户冷却（秒） |
| `PHOTO_RATE_LIMIT_SECONDS` | `10` | 以图搜番单用户冷却（秒） |
| `PHOTO_SIM_THRESHOLD` | `75` | 以图搜番相似度阈值，高于此直接出结果 |
| `CACHE_TTL` | `3600` | 搜索结果缓存（秒） |
| `TRANS_TARGET` | `zh-CN` | 翻译目标语言 |

### 进群使用

1. [@BotFather](https://t.me/BotFather) → `/setprivacy` → **Disable**（否则群里收不到消息；`/s` 命令本身不受影响）
2. 把 bot 拉进群，发 `/s MIDA-497` 即可

### 后台常驻（systemd）

```ini
# ~/.config/systemd/user/javdb-ss.service
[Unit]
Description=JavDB 搜番 Bot

[Service]
Environment=BOT_TOKEN=123456:ABC-DEF...
WorkingDirectory=%h/javdb-ss
ExecStart=%h/javdb-ss/venv/bin/python bot.py
Restart=always

[Install]
WantedBy=default.target
```

```bash
systemctl --user enable --now javdb-ss
```

## 🔧 实现细节

- **搜索**：`javdb code <番号>` 精确匹配，失败退化为 `javdb search --zone all` 关键词搜索
- **以图搜番**：`javdb search --image <图> --json`（后端 AVScan），相似度 ≥75% 直接出结果，否则列 Top3 候选按钮；**仅私聊可用**，群组发图静默忽略。注意：javdb 部分候选失败时会非 0 退出但 stdout 仍是有效 JSON，解析时要容忍
- **封面**：JavDB 图床图片是加密的，直接下载是乱码 —— 用 `javdb assets download` 解密后再上传 TG，`has_spoiler=True` 发送，临时文件发完即删
- **磁力**：`javdb magnets` 取 hash 拼 `magnet:?xt=urn:btih:`，排序规则：中字优先 → 体积降序
- **翻译**：Google 免费接口（`translate.googleapis.com/client=gtx`），失败回退原文
- **注意**：javdb 二进制会在 stdin 阻塞，调用时必须关闭 stdin

## ⚠️ 免责

本项目仅做 JavDB 公开数据的查询与展示，用于学习交流。请遵守当地法律法规。
