"""Bot 配置：全部从环境变量读取，开源时不泄露任何密钥。"""
import os


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


class Config:
    # Telegram Bot Token（从 @BotFather 获取）
    BOT_TOKEN: str = _get("BOT_TOKEN")

    # javdb-cli 二进制路径
    JAVDB_BIN: str = _get("JAVDB_BIN", os.path.expanduser("~/bin/javdb"))

    # 每次展示的磁力数量
    MAGNET_COUNT: int = int(_get("MAGNET_COUNT", "3") or 3)

    # 单用户搜索冷却（秒），防刷
    RATE_LIMIT_SECONDS: int = int(_get("RATE_LIMIT_SECONDS", "3") or 3)

    # 以图搜番单用户冷却（秒），图片识别更耗资源
    PHOTO_RATE_LIMIT_SECONDS: int = int(_get("PHOTO_RATE_LIMIT_SECONDS", "10") or 10)

    # 以图搜番相似度阈值：高于此值直接出结果，否则列候选
    PHOTO_SIM_THRESHOLD: float = float(_get("PHOTO_SIM_THRESHOLD", "75") or 75)

    # 结果内存缓存 TTL（秒），减轻 javdb-cli 调用压力
    CACHE_TTL: int = int(_get("CACHE_TTL", "3600") or 3600)

    # Google 翻译目标语言
    TRANS_TARGET: str = _get("TRANS_TARGET", "zh-CN")


config = Config()
