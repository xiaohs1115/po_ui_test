"""
AI 服务配置统一入口。
切换提供方只需修改 .env，代码零改动。

.env 配置示例
─────────────────────────────────────────
DeepSeek（默认）:
  AI_API_KEY=sk-xxx
  AI_BASE_URL=https://api.deepseek.com
  AI_MODEL=deepseek-chat

OpenAI:
  AI_API_KEY=sk-xxx
  AI_BASE_URL=https://api.openai.com/v1
  AI_MODEL=gpt-4o

通义千问:
  AI_API_KEY=sk-xxx
  AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
  AI_MODEL=qwen-plus

Moonshot:
  AI_API_KEY=sk-xxx
  AI_BASE_URL=https://api.moonshot.cn/v1
  AI_MODEL=moonshot-v1-8k
─────────────────────────────────────────
"""
import os


def api_key() -> str:
    return os.environ.get("AI_API_KEY", "")


def base_url() -> str:
    return os.environ.get("AI_BASE_URL", "https://api.deepseek.com")


def model() -> str:
    return os.environ.get("AI_MODEL", "deepseek-chat")


def require_api_key() -> str:
    """获取 API Key，未配置时给出明确提示。"""
    key = api_key()
    if not key:
        raise RuntimeError(
            "AI_API_KEY 未设置\n"
            "  本地：在 .env 文件中添加 AI_API_KEY=sk-xxx\n"
            "  CI：在 GitHub Secrets 中添加 AI_API_KEY"
        )
    return key