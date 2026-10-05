/* Opt-in acceptance of the actual Mac package; no fake runner, provider or DB copy.
 * Usage: PACKAGED_BUNDLE=/absolute/extracted/bundle PACKAGED_TEST_DIR=/private/tmp/new-dir
 *        PLAYWRIGHT_MODULE=/absolute/@playwright/test node tests/startup/packaged_entry.cjs
 * Does not prove Finder interaction, Gatekeeper or other-platform hardware support.
 */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const net = require('node:net');
const { spawn, execFileSync } = require('node:child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || '@playwright/test');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const hash = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
let stage = 'inputs', processGroup, browser, page, control, token, root;
const evidence = { mode: 'real-package-entry-browser', paid_requests: 0, stages: [] };
const record = name => { stage = name; evidence.stages.push({stage:name,at:new Date().toISOString()}); console.log(name); };
async function request(action, body) {
 const r = await fetch(control.origin + '/control/' + action, {method:body===undefined?'GET':'POST',headers:{Origin:control.origin,'Content-Type':'application/json',Authorization:'Bearer '+token},...(body===undefined?{}:{body:JSON.stringify(body)})});
 assert.equal(r.status,200,'control operation failed'); return r.json();
}
async function waitPhase(phase, limit=240000) {
 const deadline=Date.now()+limit;
 while(Date.now()<deadline){ const s=await request('status'); if(s.phase===phase&&!s.busy)return s; if(s.failure&&!s.busy)throw new Error('control failure'); await sleep(2000); }
 throw new Error('phase deadline');
}
async function initPage() {
 control=JSON.parse(fs.readFileSync(path.join(root,'control.json'),'utf8'));
 token=control.key;
 const seed=await request('reopen',{});
 const exchanged=page.waitForResponse(r=>r.url()===control.origin+'/control/exchange'&&r.status()===200);
 await page.goto(control.origin+'/#'+seed.fragment);
 token=(await (await exchanged).json()).token;
 await page.waitForFunction(()=>document.querySelector('#status').textContent!=='正在连接本机启动器…');
 assert.equal(await page.evaluate(()=>location.hash),'');
}
async function login(webURL, name, password) {
 const app=await browser.newPage();
 // Reject browser requests outside loopback rather than using any real AI provider.
 await app.route('**/*',route=>{const u=new URL(route.request().url());return u.hostname==='127.0.0.1'?route.continue():route.abort();});
 await app.goto(webURL);
 await app.locator('input[name=username]').fill(name); await app.locator('input[name=password]').fill(password);
 const response=app.waitForResponse(r=>r.url().endsWith('/api/v1/auth/login'));
 await app.getByRole('button',{name:'登录',exact:true}).click();
 const r=await response; assert.equal(r.status(),200); const body=await r.json();
 assert.equal(body.user.username,name); assert.equal(body.user.role,'teacher');
 await app.waitForURL('**/teacher'); await app.locator('body').filter({hasText:'课程'}).waitFor();
 assert.ok(!await app.getByText('演示模式',{exact:true}).isVisible());
 await app.screenshot({path:path.join(process.env.PACKAGED_TEST_DIR,'teacher-login.png'),fullPage:true});
 await app.close();
}
(async()=>{
 assert.equal(process.platform,'darwin');
 const bundle=fs.realpathSync(process.env.PACKAGED_BUNDLE);
 const dir=process.env.PACKAGED_TEST_DIR; assert.ok(dir&&path.isAbsolute(dir)&&dir.startsWith('/private/tmp/'));
 fs.mkdirSync(dir,{mode:0o700}); const home=path.join(dir,'home');fs.mkdirSync(home,{mode:0o700});
 root=path.join(home,'Library','Application Support','SmartSketch');
 const manifest=JSON.parse(fs.readFileSync(path.join(bundle,'release-manifest.json'),'utf8'));
 assert.equal(hash(path.join(bundle,'compose.release.yaml')),manifest.compose_sha256);
 for(const key of ['backend_image','frontend_image','neo4j_image'])assert.match(manifest[key],/@sha256:[a-f0-9]{64}$/);
 assert.equal(fs.readFileSync(path.join(bundle,'target.txt'),'utf8').trim(),'darwin-'+(os.arch()==='x64'?'amd64':'arm64'));
 const entry=path.join(bundle,'start-macos.command');assert.ok(fs.statSync(entry).mode&0o100);
 evidence.manifest=manifest; evidence.entry_sha256=hash(entry);
 const env={HOME:home,USER:os.userInfo().username,LANG:'en_US.UTF-8',PATH:path.join(os.homedir(),'.docker','bin')+':/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',DOCKER_CONFIG:path.join(os.homedir(),'.docker'),TMPDIR:'/private/tmp'};
 const out=fs.openSync(path.join(dir,'entry.log'),'wx',0o600);
 record('actual-entry-start');
 processGroup=spawn(entry,[],{cwd:bundle,env,detached:true,stdio:['ignore',out,out]});
 for(let i=0;i<150&&!fs.existsSync(path.join(root,'control.json'));i++){assert.equal(processGroup.exitCode,null);await sleep(200);}
 assert.ok(fs.existsSync(path.join(root,'control.json')));
 browser=await chromium.launch({headless:true,executablePath:process.env.STARTUP_BROWSER_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 page=await browser.newPage();await initPage(); await page.locator('#setup').waitFor({state:'visible'});
 record('real-wizard-ready');
 const server=net.createServer(); await new Promise(r=>server.listen(0,'127.0.0.1',r)); const port=server.address().port;await new Promise(r=>server.close(r));
 const name='teacher_package'; const password='fixture-package-pass-2026';
 for(const [field,value] of Object.entries({base_url:'https://example.com/v1',model:'fixture-vector',dimensions:'1024',api_key:'fixture-package-key',teacher_username:name,teacher_password:password,confirm_password:'different-password',web_port:String(port)}))await page.locator('#setup-form [name="'+field+'"]').fill(value);
 await page.locator('#install').click();await page.waitForFunction(()=>document.querySelector('#message').textContent.length>0);
 assert.ok(!fs.existsSync(path.join(root,'.env')));assert.equal((await request('status')).phase,'NEW');
 record('invalid-password-rejected-without-config');
 for(const field of ['api_key','teacher_password','confirm_password'])await page.locator('#setup-form [name="'+field+'"]').fill(field==='api_key'?'fixture-package-key':password);
 await page.locator('#install').click();await page.locator('#existing').waitFor({state:'visible'});
 const ready=await waitPhase('READY',30*60*1000);assert.equal(ready.web_port,port);assert.ok(ready.web_url);
 record('pinned-pull-services-schema-indexes-ready');
 assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
 for(const input of await page.locator('input[type=password]').all())assert.equal(await input.inputValue(),'');
 await page.screenshot({path:path.join(dir,'wizard-ready.png'),fullPage:true});
 const configHash=hash(path.join(root,'.env'));const initial=JSON.parse(fs.readFileSync(path.join(root,'installation.json'),'utf8'));
 await login(ready.web_url,name,password);record('teacher-browser-login');
 // A second invocation must reopen, not create/reset an installation.
 const twice=spawn(entry,[],{cwd:bundle,env,stdio:['ignore',out,out]});
 await new Promise((resolve,reject)=>{twice.on('exit',c=>c===0?resolve():reject(new Error('second entry failed')));twice.on('error',reject);});
 assert.equal(hash(path.join(root,'.env')),configHash);
 assert.equal(JSON.parse(fs.readFileSync(path.join(root,'installation.json'),'utf8')).InstallID,initial.InstallID);
 await initPage();assert.equal((await waitPhase('READY')).phase,'READY');record('repeat-entry-reuses-installation');
 page.on('dialog',d=>d.accept()); await page.locator('[data-action=stop]').click();await waitPhase('STOPPED');
 assert.equal(hash(path.join(root,'.env')),configHash);record('stop-preserves-configuration');
 await page.locator('[data-action=start]').click();const restarted=await waitPhase('READY');
 await login(restarted.web_url,name,password);record('restart-same-teacher-login');
 await request('stop',{});await waitPhase('STOPPED'); record('owned-test-installation-stopped');
 const project='smartsketch-'+initial.InstallID;
 const running=execFileSync(path.join(os.homedir(),'.docker/bin/docker'),['ps','--filter','label=com.docker.compose.project='+project,'--format','{{.ID}}'],{encoding:'utf8'});assert.equal(running.trim(),'');
 evidence.InstallID=initial.InstallID;evidence.result='PASS';
 fs.writeFileSync(path.join(dir,'acceptance.json'),JSON.stringify(evidence,null,2)+'\n',{mode:0o600});
})().catch(()=>{evidence.result='FAIL';evidence.failed_stage=stage;
 if(process.env.PACKAGED_TEST_DIR&&fs.existsSync(process.env.PACKAGED_TEST_DIR))fs.writeFileSync(path.join(process.env.PACKAGED_TEST_DIR,'acceptance.json'),JSON.stringify(evidence,null,2)+'\n',{mode:0o600});
 console.error('Package acceptance failed at: '+stage+' (no credential-bearing stack output)');process.exitCode=1;
}).finally(async()=>{
 // Best effort stop is scoped by the authenticated controller for this NEW fixture only.
 if(control&&token){try{const s=await request('status');if(s.phase!=='NEW'&&!s.busy){await request('stop',{});await waitPhase('STOPPED');}}catch{}}
 if(browser)await browser.close(); if(processGroup){try{process.kill(-processGroup.pid,'SIGINT');}catch{}await sleep(1200);try{process.kill(-processGroup.pid,'SIGTERM');}catch{}}
});
