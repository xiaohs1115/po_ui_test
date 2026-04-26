"""Page Object: tc_wa  (2 case(s))"""
import os
from .base_page import BasePage


class TcWaPage(BasePage):
    _API_KEY = os.environ["DEEPSEEK_API_KEY"]
    _BASE_URL = "https://api.deepseek.com"
    URL = "https://www.kwaixiaodian.com/?source=mianfeizhucekaidian"

    # ── tc_wa ───────────────────────────────────────

    def tc_wa_open_step1(self) -> None:
        """打开页面"""
        self.navigate(self.URL)

    def tc_wa_wait_step2(self) -> None:
        """等待2秒"""
        self.wait(2.0)

    def tc_wa_click_step3(self) -> None:
        """如果有弹窗则点击关闭按钮"""
        self.click(
            "弹窗上的关闭按钮",
            hint_css="div[class^='ant-modal'] button[aria-label='Close']", hint_xpath="//button[contains(@class,'ant-modal-close')]",
        )

    def tc_wa_click_step4(self) -> None:
        """点击'邀新商得现金'位置"""
        self.click(
            "文字为'邀新商得现金'的按钮或区域",
            hint_css=".FirstSlideNew_progressBarItem__4m2D_.FirstSlideNew_active__93FMz .FirstSlideNew_progressBarTitle__TGzv0[class*='邀新商得现金']", hint_xpath="//div[contains(@class,'FirstSlideNew_progressBarItem') and contains(@class,'FirstSlideNew_active__93FMz')]//div[contains(@class,'FirstSlideNew_progressBarTitle') and contains(text(),'邀新商得现金')]",
        )

    def tc_wa_wait_step5(self) -> None:
        """等待1秒"""
        self.wait(1.0)

    def tc_wa_assert_text_step6(self) -> None:
        """校验页面上方轮播图中包含指定文案"""
        self.assert_text(
            "邀商家开店，得现金奖励！",
            hint_description="页面上方的轮播图区域", hint_css=".FirstSlideNew_carouselContainer__BYfk5",
        )

    # ── tc_wa_2 ─────────────────────────────────────

    def tc_wa_2_open_step1(self) -> None:
        """打开页面"""
        self.navigate(self.URL)

    def tc_wa_2_wait_step2(self) -> None:
        """等待2秒"""
        self.wait(2.0)

    def tc_wa_2_check_visible_step3(self) -> bool:
        """判断是否有弹窗（检查弹窗关闭按钮是否可见）"""
        return self.assert_visible_soft(
            "弹窗上的关闭按钮", hint_css="button.ant-modal-close",
        )

    def tc_wa_2_click_step4(self) -> None:
        """如果弹窗存在，点击关闭"""
        self.click(
            "弹窗上的关闭按钮",
            hint_css="button[aria-label='关闭']", hint_xpath="//button[@aria-label='关闭']",
        )

    def tc_wa_2_click_step5(self) -> None:
        """找到'邀新商得现金'位置并点击"""
        self.click(
            "文字为'邀新商得现金'的元素",
            hint_css="#__next .FirstSlideNew_progressBarItem:nth-child(2) .FirstSlideNew_progressBarTitle__TGzv0", hint_xpath="//div[contains(@class,'FirstSlideNew_progressBarItem')][2]//div[contains(@class,'FirstSlideNew_progressBarTitle__TGzv0')]",
        )

    def tc_wa_2_wait_step6(self) -> None:
        """等待1秒"""
        self.wait(1.0)
