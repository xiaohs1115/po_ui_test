from playwright.sync_api import sync_playwright
import json

def analyze_with_playwright(url):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        # 开始追踪（类似 Chrome DevTools 录制）
        page.context.tracing.start(screenshots=True, snapshots=True)

        response = page.goto(url, wait_until='networkidle')

        # 获取性能数据
        timing = page.evaluate("""() => {
            const nav = performance.getEntriesByType('navigation')[0];
            return {
                ttfb: Math.round(nav.responseStart - nav.requestStart),
                dom_ready: Math.round(nav.domContentLoadedEventEnd - nav.startTime),
                page_load: Math.round(nav.loadEventEnd - nav.startTime),
                transfer_kb: Math.round(nav.transferSize / 1024),
            };
        }""")

        # 获取所有网络请求耗时
        resources = page.evaluate("""() => {
            return performance.getEntriesByType('resource').map(r => ({
                name: r.name.split('/').pop(),
                type: r.initiatorType,
                duration_ms: Math.round(r.duration),
                size_kb: Math.round(r.transferSize / 1024),
            }));
        }""")

        # 保存 trace 文件（可用 Chrome 打开查看火焰图）
        page.context.tracing.stop(path="trace.zip")

        browser.close()

        print(json.dumps(timing, indent=2, ensure_ascii=False))
        print(f"\n共加载资源: {len(resources)} 个")
        for r in sorted(resources, key=lambda x: -x['duration_ms'])[:5]:
            print(f"  最慢: {r['name']} ({r['type']}) - {r['duration_ms']}ms / {r['size_kb']}KB")

        return timing, resources

analyze_with_playwright("https://www.baidu.com")