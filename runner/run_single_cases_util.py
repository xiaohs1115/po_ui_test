"""
核心执行引擎：供 run_all.py 和各 nl_cases/*.py 文件调用。
不直接运行此文件。

增量策略：
- case 名单与上次生成一致 → 跳过
- case 名单有新增/删除 → 整组重新生成
- nl_cases 中已删除的 script_name → 自动清理对应的 pages/ 和 tests/ 文件
"""
import importlib.util
import json
import os
import sys
from collections import defaultdict

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, _ROOT)

from core.nl_test_generator import (
    TestCase,
    _safe_name,
    generate_page_class,
    generate_test_file,
    run_test_case,
)

_NL_CASES_DIR = os.path.join(_ROOT, "nl_cases")
_PAGES_DIR = os.path.join(_ROOT, "pages")
_TESTS_DIR = os.path.join(_ROOT, "tests")
_MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".manifest.json")

_GENERATED_MARKER = '"""Page Object:'


def _load_manifest() -> dict[str, list[str]]:
    """读取清单：{script_safe: [case_name, ...]}"""
    try:
        with open(_MANIFEST, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_manifest(manifest: dict[str, list[str]]) -> None:
    with open(_MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def load_all_cases() -> list[TestCase]:
    """扫描 nl_cases/ 目录，收集所有 CASES 列表。"""
    cases = []
    for fname in sorted(os.listdir(_NL_CASES_DIR)):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        fpath = os.path.join(_NL_CASES_DIR, fname)
        spec = importlib.util.spec_from_file_location(fname[:-3], fpath)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cases.extend(getattr(mod, "CASES", []))
    return cases


def _is_generated(filepath: str) -> bool:
    """通过首行标志判断文件是否由本框架自动生成。"""
    try:
        with open(filepath, encoding="utf-8") as f:
            return f.readline().startswith(_GENERATED_MARKER)
    except OSError:
        return False


def _cleanup_orphans(active_script_names: set[str], manifest: dict) -> None:
    """删除已不存在对应 NL 用例的自动生成文件，并从清单中移除。"""
    for fname in os.listdir(_PAGES_DIR):
        if not fname.endswith("_page.py"):
            continue
        script_safe = fname.removesuffix("_page.py")
        if script_safe in active_script_names:
            continue
        page_file = os.path.join(_PAGES_DIR, fname)
        if not _is_generated(page_file):
            continue
        test_file = os.path.join(_TESTS_DIR, f"test_{script_safe}.py")
        os.remove(page_file)
        print(f"🗑  已删除孤立文件: {page_file}")
        if os.path.exists(test_file):
            os.remove(test_file)
            print(f"🗑  已删除孤立文件: {test_file}")
        manifest.pop(script_safe, None)


def run_cases(cases: list[TestCase]) -> None:
    """执行给定用例列表，跳过已生成的，清理已删除的，生成新增的。"""
    if not cases:
        print("没有可执行的用例")
        return

    groups: dict[str, list[TestCase]] = defaultdict(list)
    for case in cases:
        groups[_safe_name(case.script_name)].append(case)

    manifest = _load_manifest()
    _cleanup_orphans(set(groups.keys()), manifest)

    to_run: dict[str, list[TestCase]] = {}
    skipped: list[str] = []
    for script_safe, group in groups.items():
        page_file = os.path.join(_PAGES_DIR, f"{script_safe}_page.py")
        test_file = os.path.join(_TESTS_DIR, f"test_{script_safe}.py")
        current_names = sorted(c.name for c in group)
        recorded_names = sorted(manifest.get(script_safe, []))
        files_exist = os.path.exists(page_file) and os.path.exists(test_file)
        if files_exist and current_names == recorded_names:
            skipped.append(script_safe)
        else:
            to_run[script_safe] = group

    if skipped:
        print(f"⏭  跳过（已存在）：{skipped}")
    if not to_run:
        print("✅ 所有用例均已生成，无需重新执行")
        return

    pending = [c for group in to_run.values() for c in group]
    print(f"▶  待生成 {len(pending)} 个用例：{[c.name for c in pending]}")

    completed: dict[str, list[TestCase]] = defaultdict(list)
    for case in pending:
        run_test_case(case, save_script=False)
        completed[_safe_name(case.script_name)].append(case)

    for script_safe, group in completed.items():
        page_file = os.path.join(_PAGES_DIR, f"{script_safe}_page.py")
        test_file = os.path.join(_TESTS_DIR, f"test_{script_safe}.py")

        with open(page_file, "w", encoding="utf-8") as f:
            f.write(generate_page_class(group))
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(generate_test_file(group))

        manifest[script_safe] = sorted(c.name for c in group)
        print(f"\n📝 Page Object : {page_file}")
        print(f"📝 测试文件    : {test_file}  ({len(group)} 个 case)")

    _save_manifest(manifest)