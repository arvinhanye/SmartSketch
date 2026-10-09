"""Wizard guidance (release fix batch): ordinary users must know what to enter in the vector fields.

Real browser against a synthetic loopback control service; never paid APIs, no real keys.
"""
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / 'launcher/internal/launch/ui'

SCRIPT = r'''
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || '@playwright/test');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.STARTUP_BROWSER_PATH?{executablePath:process.env.STARTUP_BROWSER_PATH}:{})});
 try {
  const page=await browser.newPage();
  await page.goto(process.env.WIZARD_URL+'/#fixture-seed');
  await page.locator('#setup').waitFor({state:'visible'});
  const val=n=>page.locator('#setup [name='+n+']').inputValue();

  // 1. Default: the verified Alibaba Bailian preset is prefilled, so a normal user only needs the key.
  assert.equal(await page.locator('#vector-preset').inputValue(),'bailian');
  assert.equal(await val('base_url'),'https://dashscope.aliyuncs.com/compatible-mode/v1');
  assert.equal(await val('model'),'text-embedding-v4');
  assert.equal(await val('dimensions'),'1024');

  // 2. Plain-language guidance: what the vector service is, that this is the system default, and that
  //    teachers can override it per course inside the software.
  const setup=await page.locator('#setup').innerText();
  assert.match(setup,/系统默认/);
  assert.match(setup,/教师.*模型 API 设置.*课程单独/s);
  assert.match(setup,/生成模型.*登录后/s);
  // dimension: the default is not universal and cannot be changed after the index is built
  assert.match(setup,/不是所有模型通用/);
  assert.match(setup,/建立索引后不能更改|创建索引后不能更改/);

  // 3. Every field has a help text wired through aria-describedby (screen readers and sighted users alike).
  for(const name of ['base_url','model','dimensions','api_key','teacher_username','teacher_password','web_port']){
    const id=await page.locator('#setup [name='+name+']').getAttribute('aria-describedby');
    assert.ok(id,'missing aria-describedby on '+name);
    const text=(await page.locator('#'+id.split(' ')[0]).innerText()).trim();
    assert.ok(text.length>=6,'empty help text for '+name);
  }

  // 4. Custom provider: clears the address and model, keeps the dimension, focuses the address field.
  await page.locator('#vector-preset').selectOption('custom');
  assert.equal(await val('base_url'),'');
  assert.equal(await val('model'),'');
  assert.equal(await val('dimensions'),'1024');
  assert.equal(await page.evaluate(()=>document.activeElement&&document.activeElement.name),'base_url');

  // 5. Back to the preset restores all three values.
  await page.locator('#vector-preset').selectOption('bailian');
  assert.equal(await val('base_url'),'https://dashscope.aliyuncs.com/compatible-mode/v1');
  assert.equal(await val('model'),'text-embedding-v4');

  // 6. Editing a preset field by hand switches the selector to "custom" so the label never lies.
  await page.locator('#setup [name=model]').fill('another-model');
  assert.equal(await page.locator('#vector-preset').inputValue(),'custom');

  // 7. The key field stays a password field and is never prefilled.
  assert.equal(await page.locator('#setup [name=api_key]').getAttribute('type'),'password');
  assert.equal(await val('api_key'),'');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
'''


def test_wizard_explains_vector_fields_and_offers_a_verified_preset():
    state = {'phase': 'NEW', 'busy': False, 'actions': ['setup'], 'stage': '', 'needs_teacher': False}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path == '/control/status':
                data, content = json.dumps(state).encode(), 'application/json'
            else:
                name = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}.get(self.path)
                if name is None:
                    self.send_error(404)
                    return
                data = (UI / name).read_bytes()
                content = {'index.html': 'text/html', 'app.js': 'text/javascript', 'style.css': 'text/css'}[name]
            self.send_response(200)
            self.send_header('Content-Type', content)
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            assert self.path == '/control/exchange', 'unexpected operation'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'token': 'fixture-page-token'}).encode())

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = dict(os.environ, WIZARD_URL=f'http://127.0.0.1:{server.server_port}')
        result = subprocess.run(['node', '-e', SCRIPT], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
