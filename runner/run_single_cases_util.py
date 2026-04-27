"""
核心执行引擎：供 run_all.py 和各 nl_cases/*.py 文件调用。
不直接运行此文件。

增量策略：
- case nl_description 未变 → 跳过执行，复用 manifest 中的步骤
- case 新增或 nl_description 有变化 → 重新执行
- nl_cases 中已删除的 script_name → 自动清理对应的 pages/ 和 tests/ 文件
"""
import dataclasses
import hashlib
import importlib.util
import json
import os
import sys
from collections import defaultdict

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, _ROOT)

from core.nl_test_generator import (
    TestCase,
    TestStep,
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


def _case_hash(case: TestCase) -> str:
    return hashlib.md5(case.nl_description.strip().encode()).hexdigest()


def _steps_to_json(steps: list[TestStep]) -> list[dict]:
    return [dataclasses.asdict(s) for s in steps]


def _steps_from_json(data: list[dict]) -> list[TestStep]:
    return [TestStep(**s) for s in data]


def _load_manifest() -> dict:
    """读取清单：{script_safe: {case_name: {hash, steps}}}"""
    try:
        with open(_MANIFEST, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_manifest(manifest: dict) -> None:
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


def run_cases(cases: list[TestCase], cleanup_orphans: bool = False) -> None:
    """
    执行给定用例列表。

    - nl_description 未变的 case → 直接从 manifest 复用步骤，跳过执行
    - 新增或描述有变化的 case → 重新执行
    - cleanup_orphans：是否清理不在当前用例集合中的旧生成文件
    """
    if not cases:
        print("没有可执行的用例")
        return

    groups: dict[str, list[TestCase]] = defaultdict(list)
    for case in cases:
        groups[_safe_name(case.script_name)].append(case)

    manifest = _load_manifest()
    if cleanup_orphans:
        _cleanup_orphans(set(groups.keys()), manifest)

    any_change = False

    for script_safe, group in groups.items():
        # project 子目录（同 script_name 下的 case 必须属于同一 project）
        project_safe = _safe_name(group[0].project) if group[0].project else ""
        tests_dir = os.path.join(_TESTS_DIR, project_safe) if project_safe else _TESTS_DIR

        page_file = os.path.join(_PAGES_DIR, f"{script_safe}_page.py")
        test_file = os.path.join(tests_dir, f"test_{script_safe}.py")
        script_manifest = manifest.get(script_safe, {})

        # 兼容旧格式（list → 视为全部未知，强制重新生成）
        if isinstance(script_manifest, list):
            script_manifest = {}

        to_run: list[TestCase] = []
        to_skip: list[TestCase] = []

        for case in group:
            cached = script_manifest.get(case.name, {})
            if (
                cached
                and cached.get("hash") == _case_hash(case)
                and os.path.exists(page_file)
                and os.path.exists(test_file)
            ):
                case.steps = _steps_from_json(cached["steps"])
                to_skip.append(case)
            else:
                to_run.append(case)

        if to_skip and not to_run:
            print(f"⏭  跳过（已存在）：{script_safe}  {[c.name for c in to_skip]}")
            continue

        if to_skip:
            print(f"⏭  复用已有步骤：{[c.name for c in to_skip]}")
        if to_run:
            print(f"▶  待生成 {len(to_run)} 个用例：{[c.name for c in to_run]}")

        for case in to_run:
            run_test_case(case, save_script=False)

        # 按原始顺序合并，保持文件内方法顺序稳定
        all_cases = group  # group 已按原始顺序排列，steps 已在上面填充

        os.makedirs(_PAGES_DIR, exist_ok=True)
        os.makedirs(tests_dir, exist_ok=True)
        for d in [_PAGES_DIR, _TESTS_DIR, tests_dir]:
            init = os.path.join(d, "__init__.py")
            if not os.path.exists(init):
                open(init, "w").close()

        with open(page_file, "w", encoding="utf-8") as f:
            f.write(generate_page_class(all_cases))
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(generate_test_file(all_cases))

        # 更新 manifest（只更新本组，保留其他组）
        manifest[script_safe] = {
            c.name: {"hash": _case_hash(c), "steps": _steps_to_json(c.steps)}
            for c in all_cases
        }
        _save_manifest(manifest)

        print(f"\n📝 Page Object : {page_file}")
        print(f"📝 测试文件    : {test_file}  ({len(all_cases)} 个 case)")
        any_change = True

    if not any_change:
        print("✅ 所有用例均已生成，无需重新执行")
