"""Page Object: google  (1 case(s))"""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from .base_page import BasePage


class GooglePage(BasePage):
    URL = "https://www.google.com/"

    def open_step1(self) -> None:
        """打开页面"""
        self.navigate(self.URL)

    def wait_step2(self) -> None:
        """等待页面响应"""
        self.wait(2.0)

    def fill_step3(self) -> None:
        """在搜索框输入关键词"""
        self.fill(
            "搜索输入框", "google",
            hint_css="input[name='q']", hint_xpath="//input[@name='q']",
        )

    def press_key_step4(self) -> None:
        """按下键盘 Enter 键提交搜索"""
        self.press_key("Enter")

    def wait_step5(self) -> None:
        """等待页面响应"""
        self.wait(2.0)

    def assert_text_step6(self) -> None:
        """校验页面包含指定文字"""
        self.assert_text(
            "google",
            hint_description="", hint_css="",
        )
