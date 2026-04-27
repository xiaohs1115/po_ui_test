"""
自然语言 → UI 自动化测试用例生成器

用法示例：
    python nl_test_generator.py

或在代码底部修改 DEMO_CASES 后直接运行。
"""

import hashlib
import json
import os
import re
import textwrap
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import unquote
from playwright.sync_api import sync_playwright, Page
from bs4 import BeautifulSoup
from openai import OpenAI

# 当 AI 生成的选择器在页面上不存在时，按动作类型依次尝试的降级链
_FILL_FALLBACKS = [
    '[contenteditable="true"]',
    '#chat-input-area',
    'textarea:visible',
    'input[name="wd"]',
    '#kw',
    'input[type="search"]',
    'input[type="text"]:visible',
]
_CLICK_FALLBACKS = [
    # 弹窗关闭按钮（ant-design / 通用）
    '.ant-modal-close',
    '.ant-modal-close-x',
    'button[class*="close"]',
    '[class*="modal"] [class*="close"]',
    '[class*="Modal"] [class*="close"]',
    # 通用结构选择器（无文字假设）
    '#su',
    'input[type="submit"]',
    'button[type="submit"]',
    '[aria-label="搜索"]',
    '[aria-label="发送"]',
    '[aria-label="Search"]',
    'button[class*="submit"]',
    'button[class*="search"]',
]

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from core.ai_config import require_api_key, base_url as _ai_base_url, model as _ai_model

client = OpenAI(api_key=require_api_key(), base_url=_ai_base_url())

# 提取描述关键词时过滤掉的元词
_STOP_WORDS = {'按钮', '链接', '元素', '输入框', '输入', '文本框', '选择框', '区域',
               'button', 'link', 'element', 'input', 'field', 'the', 'a', 'an',
               '的', '用于', '提交', '用来', '这个', '那个'}


def _text_fallbacks_from_description(description: str) -> list[str]:
    """
    从元素描述中动态提取关键词，生成 :has-text() 选择器。

    示例：
      "百度一下搜索提交按钮"  → button:has-text("百度一下"), input[value*="百度一下"], ...
      "登录按钮"              → button:has-text("登录"), input[value*="登录"], ...
      "Submit button"         → button:has-text("Submit"), input[value*="Submit"], ...
    """
    if not description:
        return []

    candidates: list[str] = []

    # 引号内的精确文字（最高优先级）
    candidates += re.findall(r'["""\'「」](.*?)["""\'「」]', description)

    # 中文连续词（2~6 字，过滤元词）
    for word in re.findall(r'[一-鿿]{2,6}', description):
        if word not in _STOP_WORDS:
            candidates.append(word)

    # 英文单词（过滤元词和短词）
    for word in re.findall(r'[A-Za-z]{3,}', description):
        if word.lower() not in _STOP_WORDS:
            candidates.append(word)

    selectors: list[str] = []
    for text in dict.fromkeys(candidates):   # 去重保序
        selectors += [
            f'text="{text}"',                  # Playwright 原生文本定位（精确匹配）
            f'text={text}',                    # Playwright 原生文本定位（部分匹配）
            f'button:has-text("{text}")',
            f'a:has-text("{text}")',
            f'li:has-text("{text}")',
            f'span:has-text("{text}")',
            f'div:has-text("{text}")',
            f'input[value*="{text}"]',
            f'[aria-label*="{text}"]',
        ]
    return selectors


# ══════════════════════════════════════════════════════════════
# 数据结构
# ══════════════════════════════════════════════════════════════

@dataclass
class TestStep:
    step_id: int
    action: str           # navigate / fill / click / assert_text / assert_visible / assert_url
    description: str
    url: Optional[str] = None           # navigate 用
    element_description: Optional[str] = None  # 需要定位的元素
    value: Optional[str] = None         # fill / assert 用
    css: Optional[str] = None           # AI 定位后填入
    xpath: Optional[str] = None
    result: Optional[str] = None        # 执行结果: pass / fail / skip
    error: Optional[str] = None


@dataclass
class TestCase:
    name: str
    url: str
    nl_description: str
    script_name: str = ""   # 生成文件名；空时默认等于 name；同 script_name 的 case 合并到一个文件
    project: str = ""       # 所属项目/团队，决定 tests/{project}/ 子目录；留空放 tests/ 根目录
    owner: str = ""         # 负责人，留空时默认等于 script_name
    steps: list[TestStep] = field(default_factory=list)

    def __post_init__(self):
        if not self.script_name:
            self.script_name = self.name
        if not self.owner:
            self.owner = self.script_name


# ── PO 命名辅助 ───────────────────────────────────────────────────────

def _safe_name(name: str) -> str:
    ascii_part = re.sub(r'[^a-z0-9]+', '_',
                        name.lower().encode('ascii', 'ignore').decode()).strip('_')
    return ascii_part[:40] if ascii_part else hashlib.md5(name.encode()).hexdigest()[:8]


def _class_name(name: str) -> str:
    return ''.join(p.title() for p in _safe_name(name).split('_') if p) + 'Page'


def _method_name(step: TestStep, namespace: str = "") -> str:
    prefix = {
        'navigate': 'open', 'fill': 'fill', 'click': 'click',
        'assert_text': 'assert_text', 'assert_visible': 'check_visible',
        'assert_url': 'assert_url', 'wait': 'wait',
        'assert_count': 'assert_count', 'assert_each_text': 'assert_each_text',
        'press_key': 'press_key', 'close_modal': 'close_modal',
    }.get(step.action, step.action)
    base = f"{prefix}_step{step.step_id}"
    return f"{namespace}_{base}" if namespace else base


def _safe_json_loads(text: str) -> dict:
    """Parse JSON, falling back to regex extraction and trailing-comma repair."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Extract the first {...} block in case of extra wrapping text
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        candidate = m.group(0)
        # Remove trailing commas before } or ]
        candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    return {}


# ══════════════════════════════════════════════════════════════
# Phase 1: 自然语言 → 结构化步骤
# ══════════════════════════════════════════════════════════════

def parse_nl_to_steps(test_case: TestCase) -> list[TestStep]:
    """
    用 AI 把自然语言测试描述解析为结构化步骤列表。
    不需要打开浏览器，纯文本处理。
    """
    prompt = f"""你是一个 UI 自动化测试专家，负责将自然语言测试描述转换为结构化测试步骤。

测试用例名称：{test_case.name}
目标页面 URL：{test_case.url}
测试描述：
{test_case.nl_description}

请将上述描述解析为 JSON 格式的步骤列表，每个步骤必须包含以下字段：

{{
  "steps": [
    {{
      "step_id": 1,
      "action": "navigate",
      "description": "打开页面",
      "url": "页面 URL（仅 navigate 步骤填写）"
    }},
    {{
      "step_id": 2,
      "action": "fill",
      "description": "在搜索框输入关键词",
      "element_description": "搜索输入框的自然语言描述（供后续定位使用）",
      "value": "要输入的内容"
    }},
    {{
      "step_id": 3,
      "action": "click",
      "description": "点击提交按钮",
      "element_description": "按钮的自然语言描述"
    }},
    {{
      "step_id": 4,
      "action": "assert_text",
      "description": "校验页面包含指定文字",
      "element_description": "包含文字的元素描述（留空则在整个 body 中查找）",
      "value": "期望包含的文字"
    }},
    {{
      "step_id": 5,
      "action": "assert_visible",
      "description": "校验元素可见",
      "element_description": "目标元素描述"
    }},
    {{
      "step_id": 6,
      "action": "assert_url",
      "description": "校验当前 URL",
      "value": "URL 中应包含的字符串"
    }},
    {{
      "step_id": 7,
      "action": "wait",
      "description": "等待页面响应",
      "value": "等待秒数，纯数字字符串，如 3"
    }},
    {{
      "step_id": 8,
      "action": "assert_count",
      "description": "校验结果条数大于0",
      "element_description": "要统计的元素描述",
      "value": "期望的最少数量，纯数字字符串，如 1"
    }},
    {{
      "step_id": 9,
      "action": "assert_each_text",
      "description": "校验每条结果标题均包含指定文字",
      "element_description": "要遍历的每个元素描述（如每条搜索结果的标题）",
      "value": "每个元素中应包含的文字"
    }},
    {{
      "step_id": 10,
      "action": "press_key",
      "description": "按下键盘 Enter 键提交搜索",
      "value": "Enter"
    }},
    {{
      "step_id": 11,
      "action": "close_modal",
      "description": "如果有弹窗则关闭，没有则忽略"
    }}
  ]
}}

action 只能是这 11 种：navigate / fill / click / assert_text / assert_visible / assert_url / wait / assert_count / assert_each_text / press_key / close_modal
第一个步骤通常是 navigate。
press_key 专门用于键盘按键操作（如 Enter、Tab、Escape），value 填键名；不要用 click 代替键盘操作。
close_modal 专门用于"如果有弹窗则关闭，没有则忽略"这类条件性关闭弹窗操作，不需要 element_description；禁止用 click 代替此操作。

重要约束：
1. element_description 必须描述用户**看到的视觉特征**（按钮上的文字、输入框的占位符、标签文字等），
   禁止使用 id/class 等内部属性（如不能写"id为su的按钮"，要写"文字为'百度一下'的按钮"）。
2. assert_text 的 value 必须是页面上**真实会出现的文字**，不能是对测试行为的描述（如不能写"搜索结果"，
   要写搜索关键词本身或结果标题中必然出现的词，如输入的 value 值）。
3. assert_url 的 value 填 URL 中必然出现的字符串片段（如 wd 参数值、路径等）。"""

    response = client.chat.completions.create(
        model=_ai_model(),
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        stream=False
    )
    content = response.choices[0].message.content or "{}"
    data = _safe_json_loads(content)

    steps = []
    for s in data.get("steps", []):
        steps.append(TestStep(
            step_id=s.get("step_id", len(steps) + 1),
            action=s.get("action", ""),
            description=s.get("description", ""),
            url=s.get("url"),
            element_description=s.get("element_description"),
            value=s.get("value"),
        ))
    return steps


# ══════════════════════════════════════════════════════════════
# Phase 2: AI 定位页面元素（复用 page_analyze_pro 的思路）
# ══════════════════════════════════════════════════════════════

def extract_html(page: Page) -> str:
    soup = BeautifulSoup(page.content(), 'html.parser')
    for tag in soup(['script', 'style', 'svg', 'noscript', 'meta', 'link', 'textarea']):
        tag.decompose()
    keep = {'id', 'name', 'class', 'type', 'placeholder', 'aria-label',
            'role', 'href', 'value', 'data-testid', 'contenteditable'}
    for tag in soup.find_all(True):
        for attr in [a for a in tag.attrs if a not in keep]:
            del tag[attr]
    return str(soup)[:10000]


def ai_find_element(html: str, element_description: str) -> tuple[str, str]:
    """返回 (css_selector, xpath)"""
    prompt = f"""根据以下 HTML 片段，为目标元素生成最稳定的定位器。

目标元素：{element_description}

HTML：
```html
{html}
```

严格约束：
1. 只使用 HTML 中实际存在的 id/class/属性，禁止凭知识推断
2. 优先级：id > aria-label > name > 语义标签+属性 > class

返回 JSON：
{{"css": "CSS选择器", "xpath": "XPath"}}"""

    response = client.chat.completions.create(
        model=_ai_model(),
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        stream=False
    )
    data = _safe_json_loads(response.choices[0].message.content or "{}")
    return data.get("css", ""), data.get("xpath", "")


def _verify_selectors(page: Page, css: str, xpath: str) -> bool:
    for sel in filter(None, [css, xpath]):
        try:
            if page.locator(sel).first.is_visible():
                return True
        except Exception:
            pass
    return False


def resolve_elements(page: Page, steps: list[TestStep]) -> list[TestStep]:
    """
    Phase 2：定位页面元素，补充 css/xpath。

    优先使用 Playwright MCP Server（可访问性快照，语义更准确）；
    MCP 不可用或定位失败时自动回退到原有 HTML 提取模式。
    """
    need = [(i, s) for i, s in enumerate(steps) if s.element_description]
    if not need:
        return steps

    current_url = page.url

    # ── 尝试 MCP 定位 ────────────────────────────────────────────
    mcp_results: list[tuple[str, str]] = []
    try:
        from core.mcp_locator import locate_elements_batch
        print("  🔌 Playwright MCP Server 定位中...")
        descs = [s.element_description for _, s in need]
        mcp_results = locate_elements_batch(current_url, descs)
    except ImportError:
        print("  ℹ️  mcp 未安装，使用 HTML 模式（pip install mcp 可启用 MCP）")
    except Exception as e:
        print(f"  ⚠️  MCP 定位异常，回退到 HTML 模式: {e}")

    # ── 逐步处理结果 ─────────────────────────────────────────────
    html_cache: dict[str, str] = {}

    for idx, (_, step) in enumerate(need):
        css, xpath = ("", "")
        mode = "HTML"

        if mcp_results and idx < len(mcp_results):
            mcp_css, mcp_xpath = mcp_results[idx]
            if mcp_css or mcp_xpath:
                css, xpath = mcp_css, mcp_xpath
                mode = "MCP"

        # MCP 未返回结果时回退到 HTML 模式
        if not css and not xpath:
            if current_url not in html_cache:
                html_cache[current_url] = extract_html(page)
            css, xpath = ai_find_element(html_cache[current_url], step.element_description)
            mode = "HTML"

        step.css = css
        step.xpath = xpath
        verified = _verify_selectors(page, css, xpath)
        status = f"✅ ({mode})" if verified else f"⚠️  ({mode}) 页面未验证，执行时走降级链"
        print(f"  Step {step.step_id} [{step.description}]  {status}")
        print(f"    CSS:   {css}")
        print(f"    XPath: {xpath}")

    return steps


# ══════════════════════════════════════════════════════════════
# Phase 3: 执行测试步骤
# ══════════════════════════════════════════════════════════════

def _locate(page: Page, css: str, xpath: str, timeout: int = 5000,
            fallbacks: list[str] = None):
    """
    按 CSS → XPath → fallbacks 依次尝试定位。
    找到容器 div 时自动下钻到可输入的子元素。
    """
    candidates = list(filter(None, [css, xpath])) + (fallbacks or [])
    for sel in candidates:
        try:
            el = page.locator(sel).first
            el.wait_for(state='visible', timeout=timeout)
            tag = el.evaluate("e => e.tagName.toLowerCase()")
            editable = el.evaluate("e => e.contentEditable")
            if tag not in ('input', 'textarea', 'select', 'button') and editable != 'true':
                for suffix in ['[contenteditable="true"]', 'textarea', 'input']:
                    child = page.locator(f'{sel} {suffix}').first
                    try:
                        child.wait_for(state='visible', timeout=1500)
                        return child
                    except Exception:
                        continue
            return el
        except Exception:
            continue
    return None


def execute_steps(page: Page, steps: list[TestStep]) -> list[TestStep]:
    page_changed_after_fill = False   # fill 后页面 DOM 可能变化，标记需要重新定位

    for step in steps:
        print(f"\n  Step {step.step_id}: {step.description}")
        try:
            if step.action == "navigate":
                page.goto(step.url, timeout=60000, wait_until="domcontentloaded")
                try:
                    page.wait_for_load_state('networkidle', timeout=10000)
                except Exception:
                    pass
                page_changed_after_fill = False
                step.result = "pass"

            elif step.action == "fill":
                el = _locate(page, step.css or "", step.xpath or "",
                             fallbacks=_FILL_FALLBACKS)
                if el is None:
                    raise Exception("元素未找到")
                el.click()
                page.keyboard.type(step.value or "")
                page_changed_after_fill = True   # 输入后页面结构可能已变化
                step.result = "pass"
                print(f"    → 已输入: '{step.value}'")

            elif step.action == "click":
                # fill 后页面 DOM 变了（联想词等），用当前 HTML 重新向 AI 要选择器
                if page_changed_after_fill and step.element_description:
                    print(f"    → 页面结构已变化，重新定位元素...")
                    fresh_html = extract_html(page)
                    new_css, new_xpath = ai_find_element(fresh_html, step.element_description)
                    if new_css or new_xpath:
                        step.css, step.xpath = new_css, new_xpath
                        print(f"    → 新 CSS: {new_css}")
                    page_changed_after_fill = False

                # 降级链 = 通用结构选择器 + 从描述中动态提取的文字匹配选择器
                dynamic = _text_fallbacks_from_description(step.element_description or "")
                el = _locate(page, step.css or "", step.xpath or "",
                             fallbacks=_CLICK_FALLBACKS + dynamic)
                if el is None:
                    raise Exception(f"按钮未找到（描述: {step.element_description}）—— 页面结构可能已变更")
                url_before = page.url
                try:
                    with page.context.expect_page(timeout=3000) as new_page_info:
                        el.click()
                    page = new_page_info.value
                    page.wait_for_load_state('networkidle')
                    print(f"    → 已点击（新标签页）")
                except Exception:
                    print(f"    → 已点击")
                    try:
                        page.wait_for_url(lambda url: url != url_before, timeout=4000)
                        page.wait_for_load_state('networkidle')
                    except Exception:
                        page.wait_for_timeout(2000)
                step.result = "pass"

            elif step.action == "assert_text":
                expected = step.value or ""
                if step.element_description and step.css:
                    el = _locate(page, step.css, step.xpath or "")
                    actual = el.inner_text() if el else page.locator('body').inner_text()
                else:
                    actual = page.locator('body').inner_text()
                if expected in actual:
                    step.result = "pass"
                    print(f"    → ✅ 包含文字: '{expected}'")
                else:
                    raise Exception(f"期望包含 '{expected}'，实际未找到")

            elif step.action == "assert_visible":
                el = _locate(page, step.css or "", step.xpath or "")
                if el is None:
                    step.result = "warn"
                    step.error = "元素不可见（可选检查，继续执行）"
                    print(f"    → ⚠️  元素不可见（视为可选，跳过）")
                else:
                    step.result = "pass"
                    print(f"    → ✅ 元素可见")

            elif step.action == "assert_url":
                current = unquote(page.url).lower()
                expected_url = (step.value or "").lower()
                if expected_url in current:
                    step.result = "pass"
                    print(f"    → ✅ URL 包含: '{step.value}'")
                else:
                    raise Exception(f"期望 URL 包含 '{step.value}'，实际(解码后): {unquote(page.url)}")

            elif step.action == "close_modal":
                _modal_css = (
                    ".ant-modal-wrap, [class*='ant-modal'][class*='open'], "
                    "[class*='Modal'][class*='visible'], [class*='modal'][class*='show']"
                )
                _close_css = (
                    ".ant-modal-close, .ant-modal-close-x, "
                    "button[class*='close'], [class*='modal'] [class*='close-btn'], "
                    "[class*='Modal'] [class*='close']"
                )
                try:
                    page.locator(_modal_css).first.wait_for(state="visible", timeout=4000)
                    page.locator(_close_css).first.click(timeout=4000)
                    page.wait_for_load_state("networkidle")
                    step.result = "pass"
                    print(f"    → 弹窗已关闭")
                except Exception:
                    step.result = "pass"
                    print(f"    → 无弹窗，跳过")

            elif step.action == "press_key":
                key = step.value or "Enter"
                page.keyboard.press(key)
                step.result = "pass"
                print(f"    → ⌨️  已按键: '{key}'")
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass

            elif step.action == "wait":
                seconds = float(step.value or "1")
                page.wait_for_timeout(int(seconds * 1000))
                step.result = "pass"
                print(f"    → ⏳ 已等待 {seconds} 秒")

            elif step.action == "assert_count":
                sel = step.css or step.xpath or ""
                min_count = int(step.value or "1")
                count = page.locator(sel).count() if sel else 0

                # 选择器是在首页解析的，到结果页可能失效 → 重新定位
                if count == 0 and step.element_description:
                    print(f"    → 选择器返回 0，用当前页面重新定位...")
                    new_css, new_xpath = ai_find_element(
                        extract_html(page), step.element_description)
                    for new_sel in filter(None, [new_css, new_xpath]):
                        new_count = page.locator(new_sel).count()
                        if new_count > 0:
                            step.css, sel, count = new_css, new_sel, new_count
                            print(f"    → 重新定位: {new_sel}，找到 {count} 个")
                            break

                print(f"    → 找到 {count} 个元素")
                if count >= min_count:
                    step.result = "pass"
                    print(f"    → ✅ 数量满足（≥{min_count}）")
                else:
                    raise Exception(f"期望至少 {min_count} 个，实际只有 {count} 个")

            elif step.action == "assert_each_text":
                sel = step.css or step.xpath or ""
                if not sel:
                    raise Exception("缺少选择器，无法遍历元素")
                expected = step.value or ""
                # 描述或 value 中含"忽略大小写"/"case"时不区分大小写
                ignore_case = any(k in (step.description or "").lower()
                                  for k in ["忽略大小写", "case", "不区分"])
                elements = page.locator(sel).all()
                if ignore_case:
                    failed = [el.inner_text().strip() for el in elements
                              if expected.lower() not in el.inner_text().lower()]
                else:
                    failed = [el.inner_text().strip() for el in elements
                              if expected not in el.inner_text()]
                mode = "（忽略大小写）" if ignore_case else ""
                print(f"    → 共 {len(elements)} 个元素，检查是否均包含 '{expected}'{mode}")
                if not failed:
                    step.result = "pass"
                    print(f"    → ✅ 全部通过")
                else:
                    raise Exception(
                        f"{len(failed)}/{len(elements)} 个元素不包含 '{expected}'{mode}："
                        f"{[t[:40] for t in failed[:3]]}"
                    )

        except Exception as e:
            step.result = "fail"
            step.error = str(e)
            print(f"    → ❌ 失败: {e}")

    return steps


# ══════════════════════════════════════════════════════════════
# Phase 4: 生成 PO 结构脚本
# ══════════════════════════════════════════════════════════════

def _emit_page_methods(lines: list[str], case: TestCase, namespace: str) -> None:
    """将一个 case 的所有步骤作为方法追加到 lines 中。"""
    for step in case.steps:
        method = _method_name(step, namespace)
        desc = step.description.replace('"', '\\"')
        el_desc = (step.element_description or "").replace('"', '\\"')
        css = (step.css or "").replace('"', '\\"')
        xpath = (step.xpath or "").replace('"', '\\"')
        val = (step.value or "").replace('"', '\\"')

        if step.action == "navigate":
            lines += [
                f"    def {method}(self) -> None:",
                f'        """{desc}"""',
                f"        self.navigate(self.URL)",
                "",
            ]
        elif step.action == "close_modal":
            lines += [
                f"    def {method}(self) -> None:",
                f'        """{desc}"""',
                f"        self.close_modal_if_present()",
                "",
            ]
        elif step.action == "press_key":
            lines += [
                f"    def {method}(self) -> None:",
                f'        """{desc}"""',
                f'        self.press_key("{val or "Enter"}")',
                "",
            ]
        elif step.action == "wait":
            lines += [
                f"    def {method}(self) -> None:",
                f'        """{desc}"""',
                f"        self.wait({float(step.value or 1)})",
                "",
            ]
        elif step.action == "fill":
            lines += [
                f"    def {method}(self) -> None:",
                f'        """{desc}"""',
                f"        self.fill(",
                f'            "{el_desc}", "{val}",',
                f'            hint_css="{css}", hint_xpath="{xpath}",',
                f"        )",
                "",
            ]
        elif step.action == "click":
            lines += [
                f"    def {method}(self) -> None:",
                f'        """{desc}"""',
                f"        self.click(",
                f'            "{el_desc}",',
                f'            hint_css="{css}", hint_xpath="{xpath}",',
                f"        )",
                "",
            ]
        elif step.action == "assert_visible":
            lines += [
                f"    def {method}(self) -> bool:",
                f'        """{desc}"""',
                f"        return self.assert_visible_soft(",
                f'            "{el_desc}", hint_css="{css}",',
                f"        )",
                "",
            ]
        elif step.action == "assert_text":
            lines += [
                f"    def {method}(self) -> None:",
                f'        """{desc}"""',
                f"        self.assert_text(",
                f'            "{val}",',
                f'            hint_description="{el_desc}", hint_css="{css}",',
                f"        )",
                "",
            ]
        elif step.action == "assert_url":
            lines += [
                f"    def {method}(self) -> None:",
                f'        """{desc}"""',
                f'        self.assert_url_contains("{val}")',
                "",
            ]
        elif step.action == "assert_count":
            sel = css or xpath or ""
            lines += [
                f"    def {method}(self) -> None:",
                f'        """{desc}"""',
                f'        self.assert_count("{sel}", min_n={int(val or 1)})',
                "",
            ]
        elif step.action == "assert_each_text":
            sel = css or xpath or ""
            lines += [
                f"    def {method}(self) -> None:",
                f'        """{desc}"""',
                f'        self.assert_each_text("{sel}", "{val}")',
                "",
            ]


def generate_page_class(cases: list[TestCase]) -> str:
    """生成 Page Object 类文件。多个 case 合并到一个类，方法名自动加 case 前缀避免冲突。"""
    base_url = str(client.base_url).rstrip('/')
    first = cases[0]
    cls = _class_name(first.script_name)
    multi = len(cases) > 1

    lines: list[str] = [
        f'"""Page Object: {first.script_name}  ({len(cases)} case(s))"""',
        "import os",
        "try:",
        "    from dotenv import load_dotenv",
        "    load_dotenv()",
        "except ImportError:",
        "    pass",
        "from .base_page import BasePage",
        "",
        "",
        f"class {cls}(BasePage):",
        f'    URL = "{first.url}"',
        "",
    ]

    for case in cases:
        ns = _safe_name(case.name) if multi else ""
        if multi:
            lines += [f"    # ── {case.name} {'─' * max(0, 44 - len(case.name))}", ""]
        _emit_page_methods(lines, case, ns)

    return "\n".join(lines)


def generate_test_file(cases: list[TestCase]) -> str:
    """生成测试文件。每个 case 对应一个 test_xxx() 函数。"""
    first = cases[0]
    script_safe = _safe_name(first.script_name)
    cls = _class_name(first.script_name)
    multi = len(cases) > 1

    lines: list[str] = [
        "import os, sys",
        "sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))",
        "try:",
        "    from dotenv import load_dotenv",
        "    load_dotenv()",
        "except ImportError:",
        "    pass",
        "",
        "import pytest",
        "from playwright.sync_api import sync_playwright",
        f"from pages.{script_safe}_page import {cls}",
        "",
    ]

    for case in cases:
        ns = _safe_name(case.name) if multi else ""
        fn = _safe_name(case.name)
        owner = case.owner or case.script_name
        steps = case.steps

        project = _safe_name(case.project) if case.project else _safe_name(case.script_name)
        lines += [
            "",
            f'@pytest.mark.project("{project}")',
            f'@pytest.mark.module("{_safe_name(case.script_name)}")',
            f'@pytest.mark.owner("{owner}")',
            f"def test_{fn}(request):",
            f'    """{case.nl_description.strip()}\n    """',
            "    with sync_playwright() as p:",
            '        browser = p.chromium.launch(headless="CI" in os.environ)',
            "        _pw_page = browser.new_page()",
            f"        po = {cls}(_pw_page)",
            "        try:",
        ]

        i = 0
        while i < len(steps):
            step = steps[i]
            method = _method_name(step, ns)
            if (step.action == "assert_visible"
                    and i + 1 < len(steps)
                    and steps[i + 1].action == "click"):
                next_method = _method_name(steps[i + 1], ns)
                var = f"_visible_{step.step_id}"
                lines += [
                    f"            {var} = po.{method}()",
                    f"            if {var}:",
                    f"                po.{next_method}()",
                ]
                i += 2
            else:
                lines.append(f"            po.{method}()")
                i += 1

        lines += [
            "        except Exception:",
            "            _scr_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'report', 'screenshots')",
            "            os.makedirs(_scr_dir, exist_ok=True)",
            "            _safe_id = request.node.nodeid.replace('/', '_').replace('::', '_').replace('.py', '')",
            "            _scr_path = os.path.join(_scr_dir, f'{_safe_id}.png')",
            "            try:",
            "                po._page.screenshot(path=_scr_path, full_page=True)",
            "                try:",
            "                    from pytest_html import extras as _ext",
            "                    request.node.extra = getattr(request.node, 'extra', []) + [_ext.image(_scr_path)]",
            "                except Exception:",
            "                    pass",
            "            except Exception:",
            "                pass",
            "            raise",
            "        finally:",
            "            browser.close()",
        ]

    lines += ["", "", 'if __name__ == "__main__":', f"    test_{_safe_name(cases[0].name)}(None)"]
    return "\n".join(lines)


# kept for backward compatibility with any external callers
def generate_script(test_case: TestCase) -> str:
    api_key = client.api_key
    base_url = str(client.base_url).rstrip('/')
    fn_name = (
        re.sub(r'[^a-z0-9]+', '_',
               test_case.name.lower().encode('ascii', 'ignore').decode()).strip('_')[:40]
        or hashlib.md5(test_case.name.encode()).hexdigest()[:8]
    )

    # 自愈辅助函数模板（内嵌到生成脚本中）
    helper = f'''"""自动生成的自愈测试用例: {test_case.name}
每个元素交互都内置 AI 重定位，选择器失效时自动修复。
"""
import json, re
from bs4 import BeautifulSoup
from openai import OpenAI
from playwright.sync_api import sync_playwright, Page

_client = OpenAI(api_key="{api_key}", base_url="{base_url}")


def _html(page: Page) -> str:
    soup = BeautifulSoup(page.content(), "html.parser")
    for t in soup(["script","style","svg","noscript","meta","link","textarea"]):
        t.decompose()
    keep = {{"id","name","class","type","placeholder","aria-label",
             "role","href","value","contenteditable"}}
    for t in soup.find_all(True):
        for a in [x for x in t.attrs if x not in keep]:
            del t[a]
    return str(soup)[:10000]


def _ai_find(page: Page, description: str, hint_css: str = "", hint_xpath: str = ""):
    """先用记录的选择器，失败则调 AI 重新定位（自愈）。"""
    # 按描述判断元素类型，加对应的通用降级链
    _is_input  = any(w in description for w in ["输入","搜索框","input","text","填写","keyword"])
    _is_button = any(w in description for w in ["按钮","button","点击","提交","submit","发送"])
    type_fallbacks = []
    if _is_input:
        type_fallbacks = [
            \'[contenteditable="true"]\', "#chat-input-area",
            "textarea:visible", \'input[name="wd"]\', "#kw",
            \'input[type="search"]\', \'input[type="text"]:visible\',
        ]
    elif _is_button:
        type_fallbacks = [
            "#su", \'input[type="submit"]\', \'button[type="submit"]\',
            \'[aria-label="搜索"]\', \'[aria-label="发送"]\',
        ]

    # 从描述中提取引号内文字或中文词，生成 has-text 选择器（按钮专用）
    text_sels = []
    for w in re.findall(r\'[\\"\\u201c\\u201d\\u2018\\u2019\\u300c\\u300d](.*?)[\\"\\u201c\\u201d\\u2018\\u2019\\u300c\\u300d]\', description):
        text_sels += [f\'button:has-text("{{w}}")\', f\'input[value*="{{w}}"]\', f\'a:has-text("{{w}}")\']
    for w in re.findall(r\'[\\u4e00-\\u9fff]{{2,6}}\', description):
        if w not in {{"按钮","链接","输入框","元素","提交","搜索框","首页"}}:
            text_sels += [f\'button:has-text("{{w}}")\', f\'input[value*="{{w}}"]\']

    candidates = [s for s in [hint_css, hint_xpath] if s] + type_fallbacks + text_sels

    for sel in candidates:
        try:
            el = page.locator(sel).first
            el.wait_for(state="visible", timeout=3000)
            tag = el.evaluate("e => e.tagName.toLowerCase()")
            if el.evaluate("e => e.contentEditable") == "true":
                return el
            if tag not in ("input","textarea","select","button","a"):
                for suf in [\'[contenteditable="true"]\', "textarea", "input"]:
                    child = page.locator(f"{{sel}} {{suf}}").first
                    try:
                        child.wait_for(state="visible", timeout=1500)
                        return child
                    except Exception:
                        pass
            return el
        except Exception:
            pass

    # 所有候选均失败 → 调 AI 重新生成
    print(f"  ♻️  自愈: 重新定位 {{description!r}}")
    resp = _client.chat.completions.create(
        model=_ai_model(),
        messages=[{{"role":"user","content":
            f"根据 HTML 为以下元素生成 CSS 选择器（JSON: {{{{\\\"css\\\": \\\"...\\\"}}}}):\\n元素: {{description}}\\n\\nHTML:\\n{{_html(page)}}"
        }}],
        response_format={{"type":"json_object"}},
        stream=False,
    )
    new_css = json.loads(resp.choices[0].message.content or "{{}}").get("css","")
    if new_css:
        try:
            el = page.locator(new_css).first
            el.wait_for(state="visible", timeout=5000)
            return el
        except Exception:
            pass
    raise Exception(f"无法定位元素: {{description}}")

'''

    # 测试函数体
    body_lines = [
        f"def test_{fn_name}():",
        f'    """{test_case.nl_description.strip()}"""',
        "    with sync_playwright() as p:",
        "        browser = p.chromium.launch(headless=False)",
        "        page = browser.new_page()",
        "",
    ]

    for step in test_case.steps:
        status = "✅" if step.result == "pass" else ("❌" if step.result == "fail" else "⏭")
        body_lines.append(f"        # Step {step.step_id}: {step.description}  [{status}]")

        if step.action == "navigate":
            body_lines.append(f'        page.goto("{step.url}")')
            body_lines.append('        page.wait_for_load_state("networkidle")')

        elif step.action == "fill":
            desc = (step.element_description or "").replace('"', '\\"')
            body_lines.append(
                f'        el = _ai_find(page, "{desc}", hint_css="{step.css or ""}", hint_xpath="{step.xpath or ""}")'
            )
            body_lines.append("        el.click()")
            body_lines.append(f'        page.keyboard.type("{step.value or ""}")')

        elif step.action == "click":
            desc = (step.element_description or "").replace('"', '\\"')
            body_lines.append(
                f'        el = _ai_find(page, "{desc}", hint_css="{step.css or ""}", hint_xpath="{step.xpath or ""}")'
            )
            body_lines.append("        el.click()")
            body_lines.append('        page.wait_for_load_state("networkidle")')

        elif step.action == "assert_text":
            if step.element_description and step.css:
                desc = (step.element_description or "").replace('"', '\\"')
                body_lines.append(
                    f'        el = _ai_find(page, "{desc}", hint_css="{step.css}")'
                )
                body_lines.append(f'        assert "{step.value}" in el.inner_text()')
            else:
                body_lines.append(f'        assert "{step.value}" in page.locator("body").inner_text()')

        elif step.action == "assert_visible":
            desc = (step.element_description or "").replace('"', '\\"')
            body_lines.append(f'        # 可选可见性检查：元素不存在时仅警告，不中断测试')
            body_lines.append(f'        try:')
            body_lines.append(
                f'            el = _ai_find(page, "{desc}", hint_css="{step.css or ""}")'
            )
            body_lines.append(f'            assert el.is_visible()')
            body_lines.append(f'        except Exception as _e:')
            body_lines.append(f'            print(f"    → ⚠️  可选元素未找到，跳过: {{_e}}")')

        elif step.action == "assert_url":
            body_lines.append(f'        assert "{step.value}".lower() in page.url.lower()')

        elif step.action == "wait":
            seconds = step.value or "1"
            body_lines.append(f'        page.wait_for_timeout({int(float(seconds) * 1000)})  # 等待 {seconds} 秒')

        elif step.action == "assert_count":
            sel = step.css or step.xpath or ""
            min_n = step.value or "1"
            body_lines.append(f'        _count = page.locator("{sel}").count()')
            body_lines.append(f'        print(f"    → 找到 {{_count}} 个结果")')
            body_lines.append(f'        assert _count >= {min_n}, f"期望至少 {min_n} 个，实际 {{_count}} 个"')

        elif step.action == "assert_each_text":
            sel = step.css or step.xpath or ""
            expected = step.value or ""
            body_lines.append(f'        _els = page.locator("{sel}").all()')
            body_lines.append(f'        _failed = [e.inner_text().strip() for e in _els if "{expected}" not in e.inner_text()]')
            body_lines.append(f'        print(f"    → 共 {{len(_els)}} 条，检查是否均含 \\"{expected}\\"")')
            body_lines.append(f'        assert not _failed, f"{{len(_failed)}} 条不含 \\"{expected}\\": {{[t[:40] for t in _failed[:3]]}}"')

        body_lines.append("")

    body_lines += [
        "        browser.close()",
        "",
        "",
        'if __name__ == "__main__":',
        f"    test_{fn_name}()",
    ]

    return helper + "\n".join(body_lines)


# ══════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════

def run_test_case(test_case: TestCase, save_script: bool = True):
    print(f"\n{'='*60}")
    print(f"📋 测试用例: {test_case.name}")
    print(f"{'='*60}")

    # Phase 1: 解析自然语言
    print("\n🔍 Phase 1: 解析测试描述...")
    steps = parse_nl_to_steps(test_case)
    test_case.steps = steps
    for s in steps:
        print(f"  [{s.step_id}] {s.action}: {s.description}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless="CI" in os.environ)
        page = browser.new_page()

        # 先打开页面，以便提取 HTML 用于元素定位
        try:
            page.goto(test_case.url, timeout=90000, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state('networkidle', timeout=10000)
            except Exception:
                pass
        except Exception as e:
            print(f"  ⚠️  页面加载失败: {e}")
            print("  → 跳过 Phase 2 定位，直接进入 Phase 3 执行（导航步骤会重试）")

        # Phase 2: 定位元素
        print("\n🎯 Phase 2: AI 定位元素...")
        steps = resolve_elements(page, steps)

        # Phase 3: 执行
        print("\n▶  Phase 3: 执行测试步骤...")
        steps = execute_steps(page, steps)
        test_case.steps = steps

        browser.close()

    # 统计结果
    passed = sum(1 for s in steps if s.result in ("pass", "warn"))
    failed = sum(1 for s in steps if s.result == "fail")
    warned = sum(1 for s in steps if s.result == "warn")
    print(f"\n{'='*60}")
    warn_str = f" / {warned} 警告" if warned else ""
    print(f"结果: {passed} 通过 / {failed} 失败{warn_str} / {len(steps)} 总计")
    if failed:
        print("失败步骤:")
        for s in steps:
            if s.result == "fail":
                print(f"  Step {s.step_id} [{s.description}]: {s.error}")
    if warned:
        print("警告步骤（可选检查，未中断）:")
        for s in steps:
            if s.result == "warn":
                print(f"  Step {s.step_id} [{s.description}]: {s.error}")

    # Phase 4: 生成 PO 脚本
    if save_script:
        here = os.path.dirname(os.path.abspath(__file__))
        pages_dir = os.path.join(here, "../pages")
        tests_dir = os.path.join(here, "../tests")
        os.makedirs(pages_dir, exist_ok=True)
        os.makedirs(tests_dir, exist_ok=True)
        for d in [pages_dir, tests_dir]:
            init = os.path.join(d, "__init__.py")
            if not os.path.exists(init):
                open(init, "w").close()

        safe = _safe_name(test_case.script_name)
        page_file = os.path.join(pages_dir, f"{safe}_page.py")
        test_file = os.path.join(tests_dir, f"test_{safe}.py")

        with open(page_file, "w", encoding="utf-8") as f:
            f.write(generate_page_class([test_case]))
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(generate_test_file([test_case]))

        print(f"\n📝 Page Object : {page_file}")
        print(f"📝 测试文件   : {test_file}")

    return test_case


# ══════════════════════════════════════════════════════════════
# Demo 用例
# ══════════════════════════════════════════════════════════════

DEMO_CASES = [
    # TestCase(
    #     name="baidu_search",
    #     url="https://www.baidu.com",
    #     nl_description="""
    #     打开百度首页，在搜索框输入"Claude AI"，
    #     点击文字为"百度一下"的搜索按钮，停留10秒等待页面响应，
    #     验证结果页面 URL 包含"Claude"，
    #     验证页面包含文字"Claude"，
    #     输出结果条数，
    #     验证每条结果标题中是否包含文字"Claude"(忽略Claude大小写)。
    #     """
    # ),
    TestCase(
        name="tc_wa",
        script_name="tc_wa",
        url="https://www.kwaixiaodian.com/?source=mianfeizhucekaidian",
        nl_description="""
        打开页面，等待2s，判断是否有弹窗，如果有则关闭，没有则忽略，
        找到“邀新商得现金”位置并点击，将页面动画暂停，
        判断页面上方轮播图中是否包含文案“邀商家开店，得现金奖励！”
        """
    )
]

if __name__ == "__main__":
    from collections import defaultdict

    # Phase 1-3: 依次运行每个 case（解析 + 定位 + 执行），不单独写文件
    completed: list[TestCase] = []
    for _case in DEMO_CASES:
        run_test_case(_case, save_script=False)
        completed.append(_case)

    # Phase 4: 按 script_name 分组，每组生成一份 Page Object + 一份测试文件
    _here = os.path.dirname(os.path.abspath(__file__))
    _pages_dir = os.path.join(_here, "../pages")
    _tests_dir = os.path.join(_here, "../tests")
    os.makedirs(_pages_dir, exist_ok=True)
    os.makedirs(_tests_dir, exist_ok=True)
    for _d in [_pages_dir, _tests_dir]:
        _init = os.path.join(_d, "__init__.py")
        if not os.path.exists(_init):
            open(_init, "w").close()

    _groups: dict[str, list[TestCase]] = defaultdict(list)
    for _case in completed:
        _groups[_safe_name(_case.script_name)].append(_case)

    for _script_safe, _group in _groups.items():
        _page_file = os.path.join(_pages_dir, f"{_script_safe}_page.py")
        _test_file = os.path.join(_tests_dir, f"test_{_script_safe}.py")
        with open(_page_file, "w", encoding="utf-8") as _f:
            _f.write(generate_page_class(_group))
        with open(_test_file, "w", encoding="utf-8") as _f:
            _f.write(generate_test_file(_group))
        print(f"\n📝 Page Object : {_page_file}")
        print(f"📝 测试文件   : {_test_file}  ({len(_group)} 个 case)")
