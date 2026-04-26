from core.nl_test_generator import TestCase

CASES = [
    TestCase(
        name="tc_wa",
        script_name="tc_wa",
        url="https://www.kwaixiaodian.com/?source=mianfeizhucekaidian",
        nl_description="""
        打开页面，等待2秒，判断是否有弹窗，如果有则关闭，没有则忽略，
        找到"邀新商得现金"位置并点击，等待1秒，
        判断页面上方轮播图中是否包含文案"邀商家开店，得现金奖励！"
        """,
    ),TestCase(
        name="tc_wa_2",
        script_name="tc_wa",
        url="https://www.kwaixiaodian.com/?source=mianfeizhucekaidian",
        nl_description="""
        打开页面，等待2秒，判断是否有弹窗，如果有则关闭，没有则忽略，
        找到"邀新商得现金"位置并点击，等待1秒
        """,
    )
]

if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    from runner.run_single_cases_util import run_cases
    run_cases(CASES)