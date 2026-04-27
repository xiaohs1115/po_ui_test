"""执行 nl_cases/ 下的全部自然语言用例，生成对应的 PO 文件和测试文件。"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from runner.run_single_cases_util import load_all_cases, run_cases

if __name__ == "__main__":
    # 执行全部
    run_cases(load_all_cases(), cleanup_orphans=True)