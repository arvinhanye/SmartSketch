'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const crypto=require('node:crypto');
const checks=require('./packaged_entry.cjs');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
test('failure evidence never touches existing, traversal, outside or symlink paths',()=>{
 const dir=fs.mkdtempSync('/private/tmp/smartsketch-guard-'); const evidence=path.join(dir,'acceptance.json');fs.writeFileSync(evidence,'unchanged');
 for(const target of [dir,'/Users',dir+'/../'+path.basename(dir)]){
 assert.throws(()=>checks.createOutput(target));checks.writeEvidence(null,{result:'FAIL'});assert.equal(fs.readFileSync(evidence,'utf8'),'unchanged');
 }
 const fresh=checks.createOutput(path.join(dir,'fresh'));fs.symlinkSync(evidence,path.join(fresh,'acceptance.json'));
 assert.throws(()=>checks.writeEvidence(fresh,{result:'FAIL'}));assert.equal(fs.readFileSync(evidence,'utf8'),'unchanged');
 fs.rmSync(dir,{recursive:true});
});
test('binary-only replacement fails expected provenance',()=>{
 const dir=fs.mkdtempSync('/private/tmp/smartsketch-binary-');const binary=path.join(dir,'binary');fs.writeFileSync(binary,'verified');
 checks.verifyBinary(binary,hash('verified'));fs.writeFileSync(binary,'different');assert.throws(()=>checks.verifyBinary(binary,hash('verified')));fs.rmSync(dir,{recursive:true});
});
test('busy cancellation stops only matching owned containers and records residuals',()=>{
 const calls=[];const runner=args=>{calls.push(args);if(args[0]==='ps')return calls.some(x=>x[0]==='stop')?'':'a123\n';if(args[0]==='inspect')return JSON.stringify({'io.smartsketch.installation':'0123456789abcdef','com.docker.compose.project':'smartsketch-0123456789abcdef'});return '';};
 assert.deepEqual(checks.stopOwned('0123456789abcdef',runner),{stopped:true,residual_count:0});
 assert.deepEqual(calls.find(x=>x[0]==='stop'),['stop','-t','30','a123']);
 assert.ok(calls.filter(x=>x[0]==='ps').every(x=>x.includes('label=com.docker.compose.project=smartsketch-0123456789abcdef')));
});
test('foreign labels abort cleanup without stopping any container',()=>{
 const calls=[];assert.throws(()=>checks.stopOwned('0123456789abcdef',args=>{calls.push(args);return args[0]==='ps'?'foreign\n':JSON.stringify({'io.smartsketch.installation':'other'});}));assert.ok(!calls.some(x=>x[0]==='stop'));
});
