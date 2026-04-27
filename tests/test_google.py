import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from playwright.sync_api import sync_playwright
from pages.google_page import GooglePage


def test_google_search():
    """打开页面，等待2s，输入框中输入google，
        点击enter键，等待2s，
        判断页面是否包含“google”"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless="CI" in os.environ)
        po = GooglePage(browser.new_page())

        po.open_step1()
        po.wait_step2()
        po.fill_step3()
        po.press_key_step4()
        po.wait_step5()
        po.assert_text_step6()

        browser.close()


if __name__ == "__main__":
    test_google_search()