"""
Playwright MCP Server 元素定位器。

使用可访问性快照（Accessibility Snapshot）替代原始 HTML，
让 AI 获得更丰富、更语义化的页面上下文，生成更稳定的选择器。

前置条件：
  pip install mcp
  Node.js 18+ 已安装（npx 可用）

工作原理：
  1. 启动 @playwright/mcp 作为子进程（stdio 通信）
  2. 用 MCP 浏览器打开目标页面
  3. 调用 browser_snapshot 获取可访问性树
  4. AI 根据可访问性树生成 CSS / XPath 选择器
"""
import asyncio
import json
import os
import re
import sys

from openai import OpenAI

from core.ai_config import require_api_key, base_url as _ai_base_url

_ai_client = OpenAI(api_key=require_api_key(), base_url=_ai_base_url())


def _safe_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r'\{[\s\S]*\}', text)
        if m:
            try:
                return json.loads(re.sub(r',\s*([}\]])', r'\1', m.group(0)))
            except json.JSONDecodeError:
                pass
    return {}


async def _locate_batch_async(url: str, descriptions: list[str]) -> list[tuple[str, str]]:
    """
    在单个 MCP 会话中批量定位所有元素。
    单次导航 + 单次快照，节省时间。
    """
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_params = StdioServerParameters(
        command="npx",
        args=["@playwright/mcp@latest", "--headless"],
        env={**os.environ},
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            await session.call_tool("browser_navigate", {"url": url})
            await asyncio.sleep(2)

            snap_result = await session.call_tool("browser_snapshot", {})
            snapshot = (
                snap_result.content[0].text if snap_result.content else ""
            )[:10000]

    results: list[tuple[str, str]] = []
    for desc in descriptions:
        prompt = f"""根据以下页面可访问性快照，为目标元素生成最稳定的定位器。

目标元素：{desc}

可访问性快照：
{snapshot}

严格约束：
1. 只使用快照中实际存在的属性，禁止凭知识推断
2. 优先级：aria-label > role+name > id > data-testid > class
3. 避免纯序号 / 位置类选择器（如 nth-child）

返回 JSON：{{"css": "CSS选择器", "xpath": "XPath"}}"""

        resp = _ai_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            stream=False,
        )
        data = _safe_json(resp.choices[0].message.content or "{}")
        results.append((data.get("css", ""), data.get("xpath", "")))

    return results


def locate_elements_batch(url: str, descriptions: list[str]) -> list[tuple[str, str]]:
    """
    同步入口：批量定位元素。
    MCP 不可用或失败时返回空元组列表（调用方应回退到 HTML 模式）。

    使用独立线程运行 async 代码，避免与 sync_playwright 内部 event loop 冲突。
    """
    if not descriptions:
        return []

    import threading

    results: list = [None]
    error: list = [None]

    def _run():
        # Windows 需要 ProactorEventLoop 才能运行子进程
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results[0] = loop.run_until_complete(_locate_batch_async(url, descriptions))
        except Exception as exc:
            error[0] = exc
        finally:
            loop.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=60)

    if t.is_alive():
        print("  ⚠️  MCP 定位超时（60s），回退到 HTML 模式")
        return [("", "")] * len(descriptions)

    if error[0] is not None:
        print(f"  ⚠️  MCP 定位失败: {error[0]}")
        return [("", "")] * len(descriptions)

    return results[0]