'use strict';
(() => {
 let token = ''; let working = false;
 const $ = s => document.querySelector(s);
 const stages = {environment:'检查 Docker',pull:'下载固定版本镜像（可关闭终端中断）',neo4j:'启动图数据库',migrate:'初始化数据结构',teacher:'创建教师账户',app:'启动网站与任务处理',readiness:'检查全部服务就绪',stopping:'停止服务',stopped:'已停止'};
 const message = text => { $('#message').textContent=text; };
 const clearSecrets = () => document.querySelectorAll('input[type="password"]').forEach(x=>{x.value='';});
 async function api(path, body, seed) {
  const response = await fetch('/control/'+path, {method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+(seed||token)},...(body===undefined?{}:{body:JSON.stringify(body)}),cache:'no-store'});
  const data = await response.json(); if(!response.ok) throw new Error(data.Message || '本机控制会话已失效，请重新双击启动。'); return data;
 }
 function fields(form){return Object.fromEntries(new FormData(form));}
 async function refresh(){try{const s=await api('status');$('#setup').hidden=s.phase!=='NEW';$('#existing').hidden=s.phase==='NEW';$('#resume-form').hidden=!(s.needs_teacher);$('#account-notice').textContent=s.account_notice||'';$('#status').textContent=(stages[s.stage]||s.phase)+(s.busy?' · 请稍候':'');if(s.failure)message(s.failure.Message);for(const button of document.querySelectorAll('[data-action]')){button.disabled=working||s.busy||!s.actions.includes(button.dataset.action);}$('#install').disabled=working||s.busy;}catch(e){message(e.message);}}
 $('#setup-form').addEventListener('submit',async e=>{e.preventDefault();if(working)return;working=true;const f=fields(e.target);const payload={embedding:{base_url:f.base_url,model:f.model,dimensions:Number(f.dimensions),api_key:f.api_key},teacher_username:f.teacher_username,teacher_password:f.teacher_password,confirm_password:f.confirm_password,web_port:Number(f.web_port)};try{await api('setup',payload);clearSecrets();message('配置格式检查通过；供应商连接与额度未验证。正在启动本机服务。');}catch(e){message(e.message);}finally{payload.embedding.api_key='';payload.teacher_password='';payload.confirm_password='';working=false;await refresh();}});
 document.querySelectorAll('[data-action]').forEach(button=>button.addEventListener('click',async()=>{if(working)return;const action=button.dataset.action;if(action==='stop'&&!window.confirm('停止本安装的服务并保留数据？'))return;working=true;try{let body={};if(action==='start'&&!$('#resume-form').hidden)body=fields($('#resume-form'));const result=await api(action,body);clearSecrets();if(action==='diagnostics'){const blob=new Blob([JSON.stringify(result,null,2)],{type:'application/json'});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='smartsketch-diagnostic.json';link.click();URL.revokeObjectURL(link.href);}else message('操作已接受。');}catch(e){message(e.message);}finally{working=false;await refresh();}}));
 const seed=location.hash.slice(1);history.replaceState(null,'',location.pathname);api('exchange',{},seed).then(s=>{token=s.token;refresh();setInterval(refresh,3000);}).catch(e=>message(e.message));
})();
