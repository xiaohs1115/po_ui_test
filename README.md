# po_ui_test

用自然语言描述测试意图，AI 自动生成可执行的 Page Object 自动化脚本。

---

## 核心能力

- **自然语言 → 自动化脚本**：用中文描述测试步骤，框架调用 AI 解析为结构化步骤，定位页面元素，生成 Page Object 代码
- **AI 自愈定位**：元素选择器失效时自动用当前页面 HTML 重新向 AI 要选择器，无需手动维护
- **增量生成**：基于 `nl_description` 的 MD5 哈希逐条对比，只重新执行描述发生变化或新增的用例，已有用例直接复用缓存步骤
- **多 AI 提供方**：通过 `.env` 切换 DeepSeek / OpenAI / 通义千问 / Moonshot，代码零改动
- **MCP 定位加速**：可选接入 Playwright MCP Server，用可访问性快照替代原始 HTML，生成更稳定的选择器
- **新标签页自动跟踪**：点击后若跳转到新 Tab，自动切换页面句柄，后续断言在新页面上执行
- **CI/CD 集成**：支持 GitHub Actions 定时执行、自动生成 HTML 测试报告

---

## 目录结构

```
po_ui_test/
├── .github/
│   └── workflows/
│       └── ui_test.yml               # GitHub Actions 流水线
│
├── nl_cases/                         # 自然语言用例（手动维护）
│   ├── tc_wa.py
│   └── google.py
│
├── runner/                           # 执行器
│   ├── run_all.py                    # 入口：执行全部用例
│   ├── run_single_cases_util.py      # 核心引擎（增量 + 代码生成）
│   └── .manifest.json                # 增量缓存（自动维护，勿手动编辑）
│
├── core/                             # 框架核心
│   ├── nl_test_generator.py          # AI 解析 + 定位 + 执行 + 代码生成
│   ├── ai_config.py                  # AI 提供方配置读取
│   └── mcp_locator.py                # Playwright MCP Server 定位器（可选）
│
├── pages/                            # 自动生成，勿手动编辑
│   ├── base_page.py                  # AI 自愈基类
│   ├── tc_wa_page.py
│   └── google_page.py
│
├── tests/                            # 自动生成，勿手动编辑
│   ├── test_tc_wa.py
│   └── test_google.py
│
├── conftest.py                       # pytest 根配置，自动加载 .env
├── pytest.ini                        # 固定 rootdir，支持从任意目录运行 pytest
├── requirements.txt
├── .env.example                      # 环境变量配置示例
└── .gitignore
```

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入 AI API Key（默认使用 DeepSeek）：

```env
AI_API_KEY=sk-xxx
AI_BASE_URL=https://api.deepseek.com
AI_MODEL=deepseek-chat
```

其他提供方配置示例：

| 提供方 | AI_BASE_URL | AI_MODEL |
|--------|-------------|----------|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |

### 3. 编写自然语言用例

在 `nl_cases/` 下新建文件，例如 `nl_cases/my_test.py`：

```python
from core.nl_test_generator import TestCase

CASES = [
    TestCase(
        script_name="my_test",     # 同 script_name 的 case 合并到一个 Page Object 文件
        name="case_name",
        url="https://example.com",
        nl_description="""
        打开页面，等待2秒，
        判断是否有弹窗，如果有则关闭，没有则忽略，
        在搜索框中输入"Claude"，
        点击文字为"搜索"的按钮，
        等待3秒，
        校验页面包含文字"Claude"。
        """,
    )
]

if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    from runner.run_single_cases_util import run_cases
    run_cases(CASES)
```

### 4. 执行

| 目标 | 操作 |
|------|------|
| 执行全部用例 | `python runner/run_all.py` |
| 执行单个文件 | `python nl_cases/my_test.py` |
| 用 pytest 跑生成的测试 | `pytest` 或 `pytest tests/test_my_test.py` |

执行完成后自动生成：
- `pages/my_test_page.py` — Page Object 类
- `tests/test_my_test.py` — 可直接用 pytest 运行的测试文件

---

## 自然语言写法规则

**一句话对应一个操作步骤。**

| 操作 | 写法示例 |
|------|---------|
| 打开页面 | `打开页面` |
| 等待 | `等待2秒` |
| 条件关闭弹窗 | `判断是否有弹窗，如果有则关闭，没有则忽略` |
| 输入 | `在搜索框中输入"关键词"` |
| 点击 | `找到"按钮名"位置并点击` |
| 按键 | `按下 Enter 键` |
| 校验文字 | `校验页面包含文字"期望文案"` |
| 校验 URL | `验证跳转链接是否为"https://..."` |
| 校验元素可见 | `判断"元素描述"是否可见` |
| 校验数量 | `校验搜索结果数量大于0` |
| 校验每条结果 | `校验每条结果标题均包含"关键词"（忽略大小写）` |

**关键规则：**
- 元素描述用**用户看到的文字**，不用 id / class 等技术属性
- 需要精确匹配的文案用引号括起来：`"邀商家开店，得现金奖励！"`
- 弹窗关闭用"如果有弹窗则关闭，没有则忽略"表达，框架会调用专用 `close_modal` 动作，不会误点其他元素
- 跳转到新标签页的链接无需特殊处理，框架自动切换句柄后再执行后续断言

---

## 增量策略

增量状态记录在 `runner/.manifest.json`，无需手动维护。

| 场景 | 行为 |
|------|------|
| 再次运行，`nl_description` 未变 | 跳过执行，直接复用缓存步骤重新生成文件 |
| `nl_description` 有改动 | 仅重新执行该 case |
| 新增 case | 仅执行新增的 case |
| 删除 case | 从文件中移除对应方法，清理缓存 |
| 删除整个 nl_cases 文件 | 自动清理对应的 pages/ 和 tests/ 文件 |

---

## AI 自愈机制

`BasePage.find()` 按以下优先级定位元素，全部失败才调用 AI：

1. `hint_css` / `hint_xpath`（代码中预置的选择器）
2. 按元素类型匹配通用选择器（输入框 / 按钮 / 弹窗关闭按钮）
3. 从描述文字中提取关键词，生成 `text=` / `:has-text()` 等多种选择器
4. **兜底**：把当前页面 HTML 发给 AI，重新生成 CSS 选择器

---

## Playwright MCP Server（可选）

安装后在 Phase 2 元素定位时使用可访问性快照，语义更丰富，选择器更稳定。

**前置条件：**
- Node.js 18+（`npx` 可用）
- `pip install mcp`

启用后框架自动检测；不安装则静默回退到 HTML 模式。

---

## CI/CD

### GitHub Actions 流水线

**触发条件：**

| 触发方式 | 说明 |
|---------|------|
| push 到 main | 仅当 `nl_cases/` `core/` `runner/` `pages/` `tests/` 有变更时触发 |
| Pull Request | 每次 PR 自动运行 |
| 定时任务 | 北京时间 09:00，周一至周五 |
| 手动触发 | GitHub Actions 页面点击 Run workflow |

**流水线步骤：**

```
安装依赖 + Playwright
  → python runner/run_all.py     # 增量生成/更新测试脚本
  → pytest tests/ -v             # 执行测试
  → 发布报告到 GitHub Checks
  → 上传 HTML 报告 Artifact（保留 30 天）
```

### 配置 GitHub Secret

在 `Settings → Secrets and variables → Actions` 中添加：

| 名称 | 值 |
|------|---|
| `AI_API_KEY` | AI 服务的 API Key |