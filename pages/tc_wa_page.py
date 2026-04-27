"""Page Object: tc_wa  (3 case(s))"""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from .base_page import BasePage


class TcWaPage(BasePage):
    URL = "https://www.kwaixiaodian.com/?source=mianfeizhucekaidian"

    # ── tc_wa ───────────────────────────────────────

    def tc_wa_open_step1(self) -> None:
        """打开页面"""
        self.navigate(self.URL)

    def tc_wa_wait_step2(self) -> None:
        """等待2秒，确保页面加载和弹窗出现"""
        self.wait(2.0)

    def tc_wa_close_modal_step3(self) -> None:
        """如果有弹窗则关闭，没有则忽略"""
        self.close_modal_if_present()

    def tc_wa_click_step4(self) -> None:
        """点击“邀新商得现金”位置"""
        self.click(
            "文字为'邀新商得现金'的元素",
            hint_css="div.FirstSlideNew_progressBarTitle__TGzv0:has(img):has-text('邀新商得现金')", hint_xpath="//div[contains(@class, 'FirstSlideNew_progressBarTitle') and contains(text(), '邀新商得现金')]",
        )

    def tc_wa_wait_step5(self) -> None:
        """等待1秒"""
        self.wait(1.0)

    def tc_wa_assert_text_step6(self) -> None:
        """校验页面上方轮播图中是否包含文案“邀商家开店，得现金奖励！”"""
        self.assert_text(
            "邀商家开店，得现金奖励！",
            hint_description="轮播图区域", hint_css="div.FirstSlideNew_carouselContainer__BYfk5",
        )

    # ── tc_wa_2 ─────────────────────────────────────

    def tc_wa_2_open_step1(self) -> None:
        """打开页面"""
        self.navigate(self.URL)

    def tc_wa_2_wait_step2(self) -> None:
        """等待2秒"""
        self.wait(2.0)

    def tc_wa_2_close_modal_step3(self) -> None:
        """如果有弹窗则关闭，没有则忽略"""
        self.close_modal_if_present()

    def tc_wa_2_click_step4(self) -> None:
        """点击'邀新商得现金'位置"""
        self.click(
            "文字为'邀新商得现金'的元素",
            hint_css=".FirstSlideNew_progressBarTitle__TGzv0:has(img):contains('邀新商得现金')", hint_xpath="//div[contains(@class, 'FirstSlideNew_progressBarTitle__TGzv0') and contains(., '邀新商得现金')]",
        )

    def tc_wa_2_wait_step5(self) -> None:
        """等待1秒"""
        self.wait(1.0)

    # ── jump_link ───────────────────────────────────

    def jump_link_open_step1(self) -> None:
        """打开页面"""
        self.navigate(self.URL)

    def jump_link_wait_step2(self) -> None:
        """等待2秒"""
        self.wait(2.0)

    def jump_link_close_modal_step3(self) -> None:
        """如果有弹窗则关闭，没有则忽略"""
        self.close_modal_if_present()

    def jump_link_click_step4(self) -> None:
        """点击顶部\"服务市场\"位置"""
        self.click(
            "文字为'服务市场'的链接",
            hint_css="menuitem[ref='e543'] > generic[ref='e545']", hint_xpath="//menuitem[contains(@ref,'e543')]/generic[contains(@ref,'e545')]",
        )

    def jump_link_wait_step5(self) -> None:
        """等待1秒"""
        self.wait(1.0)

    def jump_link_assert_url_step6(self) -> None:
        """验证跳转链接是否为指定URL"""
        self.assert_url_contains("https://fuwu.kwaixiaodian.com/?source=PC2025guanwang&page_version=20250731")
