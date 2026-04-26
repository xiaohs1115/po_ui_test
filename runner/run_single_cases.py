import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from runner.run_single_cases_util import run_cases
from nl_cases import tc_wa

if __name__ == "__main__":
    CASES = tc_wa.CASES
    run_cases(CASES)