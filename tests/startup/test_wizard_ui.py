"""Real browser against a synthetic loopback control service; never paid APIs."""
import json
import os
from pathlib import Path
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[2]

def test_wizard_clear_secret_and_show_real_mode():
    state = {'phase': 'NEW', 'busy': False, 'actions': ['setup'], 'stage': '', 'needs_teacher': False}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            if self.path == '/control/status':
                data = json.dumps(state).encode(); content = 'application/json'
            else:
                name = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}[self.path]
                data = (ROOT / 'launcher/internal/launch/ui' / name).read_bytes()
                content = {'index.html':'text/html','app.js':'text/javascript','style.css':'text/css'}[name]
            self.send_response(200); self.send_header('Content-Type',content); self.end_headers(); self.wfile.write(data)
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path == '/control/exchange': result = {'token': 'fixture-page-token'}
            elif self.path == '/control/setup':
                assert payload['embedding']['api_key'] == 'fixture-browser-key'
                state.update(phase='READY', actions=['open','stop','diagnostics']); result = {'accepted': True}
            else: raise AssertionError('unexpected operation')
            self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers(); self.wfile.write(json.dumps(result).encode())
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    script = r'''
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || '@playwright/test');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.STARTUP_BROWSER_PATH?{executablePath:process.env.STARTUP_BROWSER_PATH}:{})});
 try {const page=await browser.newPage();await page.goto(process.env.WIZARD_URL+'/#fixture-seed');
 await page.locator('#setup').waitFor({state:'visible'});
 for(const [name,value] of Object.entries({base_url:'https://example.com/v1',model:'fixture-vector',api_key:'fixture-browser-key',teacher_username:'teacher_one',teacher_password:'fixture-password',confirm_password:'fixture-password'}))await page.locator('[name="'+name+'"]').first().fill(value);
 await page.locator('#install').click();await page.locator('#existing').waitFor({state:'visible'});
 assert.equal(await page.evaluate(()=>location.hash),'');
 assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
 for(const input of await page.locator('input[type=password]').all())assert.equal(await input.inputValue(),'');
 assert.match(await page.locator('#message').innerText(),/供应商连接与额度未验证/);
 assert.match(await page.locator('body').innerText(),/不包含旧开发环境课程/);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
'''
    try:
        env = dict(os.environ, WIZARD_URL=f'http://127.0.0.1:{server.server_port}')
        result = subprocess.run(['node','-e',script], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)
