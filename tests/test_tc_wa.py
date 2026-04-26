import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from playwright.sync_api import sync_playwright
from pages.tc_wa_page import TcWaPage


def test_tc_wa():
    """打开页面，等待2秒，判断是否有弹窗，如果有则关闭，没有则忽略，
        找到"邀新商得现金"位置并点击，等待1秒，
        判断页面上方轮播图中是否包含文案"邀商家开店，得现金奖励！"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        po = TcWaPage(browser.new_page())

        po.tc_wa_open_step1()
        po.tc_wa_wait_step2()
        po.tc_wa_click_step3()
        po.tc_wa_click_step4()
        po.tc_wa_wait_step5()
        po.tc_wa_assert_text_step6()

        browser.close()

def test_tc_wa_2():
    """打开页面，等待2秒，判断是否有弹窗，如果有则关闭，没有则忽略，
        找到"邀新商得现金"位置并点击，等待1秒"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        po = TcWaPage(browser.new_page())

        po.tc_wa_2_open_step1()
        po.tc_wa_2_wait_step2()
        _visible_3 = po.tc_wa_2_check_visible_step3()
        if _visible_3:
            po.tc_wa_2_click_step4()

        po.tc_wa_2_click_step5()
        po.tc_wa_2_wait_step6()

        browser.close()


if __name__ == "__main__":
    test_tc_wa()