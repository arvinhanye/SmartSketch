// Read-only browser regression with fake API fixtures.
// E2E_BASE_URL points to a running Vite frontend; PLAYWRIGHT_MODULE optionally selects a bundled runtime.
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const origin = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173', cid = 'ui-fixture';
const course = { id: cid, name: '数据结构与算法', description: '浏览知识关系，检查草稿后发布。', status: 'revising', my_role: 'teacher', teacher_id: 'fixture-user', kp_count: 4, published_version: 2, created_at: '2026-10-01T00:00:00Z' };
const nodes = ['线性表', '栈', '队列', '循环队列'].map((name, i) => ({ id: 'k' + i, course_id: cid, name, aliases: [], type: 'concept', definition: name + '的基本概念。', importance: .7, difficulty: .5, level: 1, confidence: i === 2 ? .3 : .9, status: i === 2 ? 'low_confidence' : i === 3 ? 'rejected' : 'approved', source: i === 0 ? 'manual' : 'ai', locked: i === 0, revision: 1, chapter_id: 'ch1', source_refs: [] }));
const relation = { id: 'r1', course_id: cid, from_id: 'k0', to_id: 'k1', type: 'PREREQUISITE', confidence: .3, status: 'low_confidence', source: 'ai', source_refs: [{ chunk_id: 'chunk1', document_id: 'd1', page: 12 }] };
const graph = { format_version: '1.0', course_id: cid, graph_version: null, generated_at: '2026-10-01T00:00:00Z', chapters: [{ id: 'ch1', title: '线性数据结构', order: 1 }], nodes, edges: [relation] };
async function fixture(page, role = 'teacher') {
    await page.addInitScript(({ role }) => sessionStorage.setItem('smartsketch.session', JSON.stringify({ access_token: 'fixture-token', user: { id: 'fixture-user', username: 'ui_demo_' + role, role } })), { role });
    await page.route('**/api/v1/**', async (route) => {
        assert.equal(route.request().method(), 'GET', 'This regression must not write any graph data');
        const url = new URL(route.request().url()), p = url.pathname;
        let body = {}, status = 200;
        if (p === '/api/v1/courses')
            body = [course];
        else if (p.endsWith('/graph'))
            body = graph;
        else if (p.includes('/kp/')) {
            const id = p.split('/').pop();
            body = { ...nodes.find(n => n.id === id), relations: [], prerequisites: [], successors: [], related: [], sources: [] };
        }
        else if (p.startsWith('/api/v1/courses/'))
            body = { ...course, my_role: role };
        else {
            status = 404;
            body = { code: 'NOT_FOUND', message: 'fixture' };
        }
        ;
        await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    });
}
(async () => {
    const b = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined });
    try {
        for (const [width, height] of [[1920, 1080], [1440, 900], [1366, 768], [1024, 768], [390, 844]]) {
            const p = await b.newPage({ viewport: { width, height } }), errors = [];
            p.on('pageerror', e => errors.push(e.message));
            await fixture(p);
            await p.goto(origin + '/courses/' + cid + '/graph/edit');
            await p.locator('[data-test=tg-node-picker] option').nth(1).waitFor({ state: 'attached' });
            await p.locator('.gw-map').waitFor();
            await p.waitForTimeout(600);
            const measure = () => p.evaluate(() => { const c = document.querySelector('.graph-canvas').getBoundingClientRect(), m = document.querySelector('.gw-map').getBoundingClientRect(), panel = document.querySelector('.teacher-graph__panel'); return { page: document.documentElement.scrollHeight, width: document.documentElement.scrollWidth, canvas: c.height, map: m.bottom, mapTop: m.top, canvasTop: c.top, panel: panel.clientHeight, scroll: panel.scrollHeight, left: panel.getBoundingClientRect().width }; });
            const initial = await measure();
            assert(initial.page <= height + 1);
            assert(initial.width <= width);
            assert(initial.map <= height);
            assert(initial.mapTop >= initial.canvasTop);
            await p.locator('[data-test=tg-node-picker]').selectOption({ index: 1 });
            await p.locator('[data-test=tg-tab-edit]').click();
            await p.locator('[data-test=ne-name]').waitFor();
            await p.waitForTimeout(300);
            await p.locator('[data-test=ne-definition]').evaluate(e => e.style.height = '1400px');
            const edit = await measure();
            assert(edit.scroll > edit.panel);
            assert(Math.abs(initial.canvas - edit.canvas) < 1);
            assert(edit.map <= height);
            const panel = p.locator('.teacher-graph__panel');
            await panel.evaluate(e => e.scrollTop = e.scrollHeight);
            assert((await measure()).map <= height);
            await panel.evaluate(e => e.scrollTop = 0);
            if (width >= 768) {
                const divider = p.locator('[data-test=tg-panel-divider]');
                await divider.focus();
                await divider.press('ArrowRight');
                const wider = await measure();
                assert(wider.left > edit.left);
                await p.setViewportSize({ width: 900, height });
                await p.waitForTimeout(200);
                assert((await measure()).map <= height);
                await p.setViewportSize({ width, height });
                await p.waitForTimeout(200);
                await divider.press('Home');
                const min = Number(await divider.getAttribute('aria-valuenow'));
                await divider.press('ArrowLeft');
                assert.equal(Number(await divider.getAttribute('aria-valuenow')), min);
                const box = await divider.boundingBox();
                await p.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
                await p.mouse.down();
                await p.mouse.move(box.x + 100, box.y + box.height / 2);
                await p.mouse.up();
                assert(Number(await divider.getAttribute('aria-valuenow')) > min);
                assert((await measure()).map <= height);
            }
            await p.locator('[data-test=ne-close]').click();
            await p.waitForTimeout(300);
            const closed = await measure();
            assert(Math.abs(initial.canvas - closed.canvas) < 1);
            assert(closed.page <= height + 1);
            await p.locator('[data-test=gt-advanced] summary').click();
            assert.equal((await measure()).canvas, closed.canvas);
            await p.locator('[data-test=gt-advanced] summary').click();
            await p.locator('[data-test=tg-node-picker]').selectOption({ index: 1 });
            await p.locator('[data-test=ne-name]').fill('仅检查未保存提示');
            await p.locator('[data-test=ne-close]').click();
            await p.locator('[data-test=tg-discard-confirm]').waitFor();
            assert((await measure()).map <= height);
            await p.locator('[data-test=tg-discard-no]').click();
            await p.locator('[data-test=ne-close]').click();
            await p.locator('[data-test=tg-discard-yes]').click();
            assert.deepEqual(errors, []);
            console.log('PASS', width, height, initial, edit, closed);
            await p.close();
        }
    }
    finally {
        await b.close();
    }
})().catch(e => { console.error(e); process.exit(1); });
