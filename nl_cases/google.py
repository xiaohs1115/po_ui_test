from core.nl_test_generator import TestCase

CASES = [
    TestCase(
        script_name="google",
        name="google_search",
        project="merchant_growth",  # → tests / merchant_growth / test_tc_wa.py
        owner = "xiaohs",
        url="https://www.google.com/",
        nl_description="""
        打开页面，等待2s，输入框中输入google，
        点击enter键，等待2s，
        判断页面是否包含“google”
        """
    )
]

if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    from runner.run_single_cases_util import run_cases
    run_cases(CASES)