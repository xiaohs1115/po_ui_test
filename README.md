# po_ui_test

用自然语言描述测试意图，AI 自动生成可执行的 Page Object 自动化脚本。

---

## 核心能力

- **自然语言 → 自动化脚本**：用中文描述测试步骤，框架调用 DeepSeek AI 解析为结构化步骤，定位页面元素，生成 Page Object 代码
- **AI 自愈定位**：元素选择器失效时自动用当前页面 HTML 重新向 AI 要选择器，无需手动维护
- **增量生成**：已生成的用例不重复执行，新增/删除用例自动感知并同步
- **CI/CD 集成**：支持 GitHub Actions 定时执行、自动生成 HTML 测试报告

---

## 目录结构

```
po_ui_test/
├── .github/
│   └── workflows/
│       └── ui_test.yml           # GitHub Actions 流水线
│
├── nl_cases/                     # 自然语言用例（手动维护）
│   └── tc_wa.py                  # 每个文件定义一组 CASES
│
├── runner/                       # 执行器（不需要修改）
│   ├── run_all.py                # 入口：执行全部用例
│   ├── run_single_cases.py       # 入口：执行指定用例
│   └── run_single_cases_util.py  # 核心引擎
│
├── core/                         # 框架核心（不需要修改）
│   └── nl_test_generator.py      # AI 解析 + 定位 + 执行 + 代码生成
│
├── pages/                        # 自动生成，勿手动编辑
│   ├── base_page.py              # AI 自愈基类
│   └── tc_wa_page.py
│
├── tests/                        # 自动生成，勿手动编辑
│   └── test_tc_wa.py
│
├── requirements.txt
├── .env.example                  # 本地环境变量配置示例
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
# 复制示例文件
cp .env.example .env

# 填入 DeepSeek API Key
export DEEPSEEK_API_KEY=your_api_key_here
```

> PyCharm 用户：在 Run Configuration → Environment variables 中填写 `DEEPSEEK_API_KEY`。

### 3. 编写自然语言用例

在 `nl_cases/` 下新建文件，例如 `nl_cases/my_test.py`：

```python
from core.nl_test_generator import TestCase

CASES = [
    TestCase(
        script_name="my_test",
        name="case_name",
        url="https://example.com",
        nl_description="""
        打开页面，等待2秒，
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
| 执行全部用例 | 运行 `runner/run_all.py` |
| 执行单个用例 | 直接运行对应的 `nl_cases/my_test.py` |

执行完成后自动生成：
- `pages/my_test_page.py` — Page Object 类
- `tests/test_my_test.py` — 可直接用 pytest 运行的测试文件

---

## 自然语言写法规则

**一句话对应一个操作步骤。**

| 操作 | 写法示例 |
|------|---------|
| 打开页面 | `打开页面` / `访问首页` |
| 等待 | `等待2秒` |
| 输入 | `在搜索框中输入"关键词"` |
| 点击 | `点击文字为"按钮名"的按钮` |
| 条件关闭弹窗 | `判断是否有弹窗，如果有则关闭，没有则忽略` |
| 校验文字 | `校验页面包含文字"期望文案"` |
| 校验 URL | `校验页面URL包含"字符串"` |
| 校验元素可见 | `判断"元素描述"是否可见` |
| 校验数量 | `校验搜索结果数量大于0` |
| 校验每条结果 | `校验每条结果标题均包含"关键词"（忽略大小写）` |

**关键规则：**
- 元素描述用**用户看到的文字**，不用 id/class 等技术属性
- 需要精确匹配的文案用引号括起来：`"邀商家开店，得现金奖励！"`
- 条件操作用"如果...则...没有则忽略"表达

---

## 增量策略

| 场景 | 行为 |
|------|------|
| 再次运行，用例未变 | 跳过，不重新生成 |
| 在已有 `script_name` 下新增 case | 整组重新生成 |
| 删除某个 case | 整组重新生成 |
| 删除整个 nl_cases 文件 | 自动清理对应的 pages/ 和 tests/ 文件 |

增量状态记录在 `runner/.manifest.json`，无需手动维护。

---

## CI/CD

### GitHub Actions 流水线

流水线文件：`.github/workflows/ui_test.yml`

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
  → python runner/run_all.py     # 生成/增量更新测试脚本
  → pytest tests/ -v             # 执行测试
  → 发布报告到 GitHub Checks      # 在 PR/commit 页面展示结果
  → 上传 HTML 报告 Artifact       # 可下载查看详细报告
```

**测试报告：**
- **GitHub Checks**：每次运行后在 commit/PR 页面的 Checks 标签下直接展示通过/失败明细
- **HTML 报告**：Actions → 对应运行记录 → Artifacts 下载，保留 30 天

### 配置 GitHub Secret

在 GitHub 仓库 `Settings → Secrets and variables → Actions` 中添加：

| 名称 | 值 |
|------|---|
| `DEEPSEEK_API_KEY` | DeepSeek API Key |

---

## AI 自愈机制

`BasePage.find()` 按以下优先级定位元素，全部失败才调用 AI：

1. 代码中写好的 `hint_css` / `hint_xpath`
2. 按元素类型匹配通用选择器（输入框类 / 按钮类）
3. 从描述文字中提取关键词生成 `:has-text()` 选择器
4. **兜底**：把当前页面 HTML 发给 AI，重新生成 CSS 选择器