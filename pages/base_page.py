"""
BasePage: AI 自愈基类，所有 Page Object 继承此类。
提供元素定位、页面操作、断言等通用能力。
"""
import json
import os
import re
from urllib.parse import unquote

from bs4 import BeautifulSoup
from openai import OpenAI
from playwright.sync_api import Page

_MODAL_CSS = (
    ".ant-modal-wrap, [class*='ant-modal'][class*='open'], "
    "[class*='Modal'][class*='visible'], [class*='modal'][class*='show']"
)
_MODAL_CLOSE_CSS = (
    ".ant-modal-close, .ant-modal-close-x, "
    "button[class*='close'], [class*='modal'] [class*='close-btn'], "
    "[class*='Modal'] [class*='close']"
)


class BasePage:
    """AI 自愈基类：封装元素定位与常用断言。所有 Page Object 继承此类。"""

    def __init__(self, page: Page) -> None:
        self._page = page
        from core.ai_config import require_api_key, base_url
        self._client = OpenAI(api_key=require_api_key(), base_url=base_url())

    # ── 页面上下文提取 ──────────────────────────────────────────────────

    def _html(self) -> str:
        """
        优先返回可访问性快照（语义更丰富），回退到精简 HTML。
        可访问性快照包含 role / name / aria-label 等信息，
        比原始 HTML 更适合让 AI 定位交互元素。
        """
        try:
            snap = self._page.accessibility.snapshot()
            if snap:
                return json.dumps(snap, ensure_ascii=False)[:10000]
        except Exception:
            pass

        soup = BeautifulSoup(self._page.content(), "html.parser")
        for tag in soup(["script", "style", "svg", "noscript", "meta", "link", "textarea"]):
            tag.decompose()
        keep = {"id", "name", "class", "type", "placeholder", "aria-label",
                "role", "href", "value", "data-testid", "contenteditable"}
        for tag in soup.find_all(True):
            for attr in [a for a in tag.attrs if a not in keep]:
                del tag[attr]
        return str(soup)[:10000]

    # ── AI 自愈定位 ─────────────────────────────────────────────────────

    def find(self, description: str, hint_css: str = "", hint_xpath: str = ""):
        """先尝试 hint 选择器，全部失败后调 AI 重新生成。"""
        is_input = any(w in description for w in ["输入", "搜索框", "input", "text", "填写"])
        is_button = any(w in description for w in ["按钮", "button", "点击", "提交", "submit", "发送"])

        type_fallbacks: list[str] = []
        if is_input:
            type_fallbacks = [
                '[contenteditable="true"]', "#chat-input-area",
                "textarea:visible", 'input[name="wd"]', "#kw",
                'input[type="search"]', 'input[type="text"]:visible',
            ]
        elif is_button:
            type_fallbacks = [
                ".ant-modal-close", ".ant-modal-close-x",
                "button[class*='close']", "[class*='modal'] [class*='close']",
                "#su", 'input[type="submit"]', 'button[type="submit"]',
                '[aria-label="搜索"]', '[aria-label="发送"]',
            ]

        text_sels: list[str] = []
        for w in re.findall(
            '[\u201c\u201d\u2018\u2019\u300c\u300d](.*?)[\u201c\u201d\u2018\u2019\u300c\u300d]',
            description,
        ):
            text_sels += [
                f'text="{w}"', f'text={w}',
                f'button:has-text("{w}")', f'a:has-text("{w}")',
                f'li:has-text("{w}")', f'span:has-text("{w}")',
                f'div:has-text("{w}")', f'input[value*="{w}"]',
            ]
        for w in re.findall(r"[一-鿿]{2,6}", description):
            if w not in {"按钮", "链接", "输入框", "元素", "提交", "搜索框", "首页"}:
                text_sels += [
                    f'text="{w}"', f'text={w}',
                    f'button:has-text("{w}")', f'a:has-text("{w}")',
                    f'li:has-text("{w}")', f'span:has-text("{w}")',
                ]

        candidates = [s for s in [hint_css, hint_xpath] if s] + type_fallbacks + text_sels

        for sel in candidates:
            try:
                el = self._page.locator(sel).first
                el.wait_for(state="visible", timeout=3000)
                tag = el.evaluate("e => e.tagName.toLowerCase()")
                if el.evaluate("e => e.contentEditable") == "true":
                    return el
                if tag not in ("input", "textarea", "select", "button", "a"):
                    for suf in ['[contenteditable="true"]', "textarea", "input"]:
                        child = self._page.locator(f"{sel} {suf}").first
                        try:
                            child.wait_for(state="visible", timeout=1500)
                            return child
                        except Exception:
                            pass
                return el
            except Exception:
                pass

        print(f"  ♻️  自愈: 重新定位 {description!r}")
        resp = self._client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content":
                f'根据 HTML 为以下元素生成 CSS 选择器（JSON: {{"css": "..."}}）:\n'
                f"元素: {description}\n\nHTML:\n{self._html()}"
            }],
            response_format={"type": "json_object"},
            stream=False,
        )
        new_css = json.loads(resp.choices[0].message.content or "{}").get("css", "")
        if new_css:
            try:
                el = self._page.locator(new_css).first
                el.wait_for(state="visible", timeout=5000)
                return el
            except Exception:
                pass
        raise Exception(f"无法定位元素: {description}")

    # ── 页面操作 ────────────────────────────────────────────────────────

    def navigate(self, url: str) -> None:
        self._page.goto(url)
        self._page.wait_for_load_state("networkidle")

    def fill(self, description: str, value: str,
             hint_css: str = "", hint_xpath: str = "") -> None:
        el = self.find(description, hint_css, hint_xpath)
        el.click()
        self._page.keyboard.type(value)

    def click(self, description: str,
              hint_css: str = "", hint_xpath: str = "") -> None:
        el = self.find(description, hint_css, hint_xpath)
        url_before = self._page.url
        try:
            # expect_page 在点击前挂监听器，可靠捕获新标签页
            with self._page.context.expect_page(timeout=3000) as new_page_info:
                el.click()
            new_page = new_page_info.value
            new_page.wait_for_load_state("networkidle")
            self._page = new_page
        except Exception:
            # 无新标签页 → 等待当前页 URL 变化
            try:
                self._page.wait_for_url(lambda u: u != url_before, timeout=4000)
                self._page.wait_for_load_state("networkidle")
            except Exception:
                self._page.wait_for_timeout(2000)

    def press_key(self, key: str) -> None:
        self._page.keyboard.press(key)

    def wait(self, seconds: float) -> None:
        self._page.wait_for_timeout(int(seconds * 1000))

    def close_modal_if_present(
        self,
        modal_css: str = _MODAL_CSS,
        close_css: str = _MODAL_CLOSE_CSS,
        timeout: int = 4000,
    ) -> bool:
        """关闭弹窗（如有）。返回 True 表示弹窗已关闭，False 表示无弹窗。"""
        try:
            self._page.locator(modal_css).first.wait_for(state="visible", timeout=timeout)
            self._page.locator(close_css).first.click(timeout=timeout)
            self._page.wait_for_load_state("networkidle")
            print("    → 弹窗已关闭")
            return True
        except Exception:
            print("    → 无弹窗，跳过")
            return False

    # ── 断言 ────────────────────────────────────────────────────────────

    def assert_text(self, value: str,
                    hint_description: str = "", hint_css: str = "") -> None:
        if hint_description and hint_css:
            el = self.find(hint_description, hint_css)
            actual = el.inner_text()
        else:
            actual = self._page.locator("body").inner_text()
        assert value in actual, f"期望包含 '{value}'，实际未找到"

    def assert_visible_soft(self, description: str, hint_css: str = "") -> bool:
        """可选可见性检查；不存在时打印警告并返回 False，不抛出异常。"""
        try:
            el = self.find(description, hint_css)
            if el.is_visible():
                return True
            print(f"    → ⚠️  元素不可见（可选）: {description}")
            return False
        except Exception as e:
            print(f"    → ⚠️  元素未找到（可选）: {e}")
            return False

    def assert_url_contains(self, value: str) -> None:
        actual = unquote(self._page.url)
        assert value.lower() in actual.lower(), \
            f"期望 URL 包含 '{value}'，实际: {actual}"

    def assert_count(self, sel: str, min_n: int = 1) -> None:
        count = self._page.locator(sel).count()
        print(f"    → 找到 {count} 个元素")
        assert count >= min_n, f"期望至少 {min_n} 个，实际 {count} 个"

    def assert_each_text(self, sel: str, expected: str) -> None:
        els = self._page.locator(sel).all()
        failed = [e.inner_text().strip() for e in els
                  if expected.lower() not in e.inner_text().lower()]
        print(f"    → 共 {len(els)} 条，检查是否均含 '{expected}'")
        assert not failed, \
            f"{len(failed)} 条不含 '{expected}': {[t[:40] for t in failed[:3]]}"