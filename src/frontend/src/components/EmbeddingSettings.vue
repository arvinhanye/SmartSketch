<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'
import { EMBEDDING_CONFIG_API_KEY, type EmbeddingConfig } from '../api/embeddingConfig'
import type { ModelConfig, ModelConfigApi } from '../api/modelConfig'
import { MODEL_PROVIDERS, useModelDiscovery } from '../composables/useModelDiscovery'
import { useModelConfig } from '../composables/useModelConfig'
const api=inject(EMBEDDING_CONFIG_API_KEY,null)
const dimensions=ref(1024)
const customDimension=ref(false)
const dimensionOptions=[128,256,512,768,1024,1536,2048,3072,4096]
const validDimension=computed(()=>Number.isInteger(dimensions.value)&&dimensions.value>=1&&dimensions.value<=4096)
const dimensionChoice=computed(()=>customDimension.value||!dimensionOptions.includes(dimensions.value)?'custom':String(dimensions.value))
function changeDimension(event:Event) {
 const value=(event.target as HTMLSelectElement).value
 customDimension.value=value==='custom'
 if(!customDimension.value)dimensions.value=Number(value)
}
function adopt(value:EmbeddingConfig):ModelConfig {
 return {...value,runtime_mode:'personal'}
}
const bridge:ModelConfigApi={
 get:async control=>{if(!api)throw new Error('embedding API unavailable');return adopt(await api.get(control))},
 save:async(body,control)=>{
  if(!api||!validDimension.value)throw new Error('invalid dimensions')
  return adopt(await api.save({base_url:body.base_url,model:body.model,dimensions:dimensions.value,...(body.api_key?{api_key:body.api_key}:{})},control))
 },
 test:async(body,control)=>{
  if(!api||!validDimension.value)throw new Error('invalid dimensions')
  return api.test({base_url:body?.base_url??form.baseUrl,model:body?.model??form.model,dimensions:dimensions.value,
   ...(body?.api_key?{api_key:body.api_key}:form.apiKey?{api_key:form.apiKey}:{})},control)
 },
 discover:async(body,control)=>{if(!api)throw new Error('embedding API unavailable');return api.discover(body,control)},
 clear:async()=>{throw new Error('embedding clear unsupported')},
}
const {status,saved,form,configured,keyRequired,busy,saving,testing,error,notice,testResult,load,save,test}=useModelConfig({api:bridge,syncRuntime:false})
const {models,loading:discovering,message:discoveryMessage,provider,canDiscover,chooseProvider,refresh}=useModelDiscovery(bridge,form,saved)
const savedDimensions=computed(()=>(saved.value as (ModelConfig & {dimensions:number})|null)?.dimensions??1024)
watch(savedDimensions,value=>{dimensions.value=value;customDimension.value=!dimensionOptions.includes(value)})
const providers=MODEL_PROVIDERS.filter(p=>p.id!=='deepseek')
const selectedProvider=computed(()=>providers.some(p=>p.id===provider.value)?provider.value:'custom')
watch(dimensions,()=>{testResult.value=null})
</script>

<template>
 <section class="embedding-settings" data-test="embedding-settings" aria-labelledby="em-title">
  <div class="ui-config-section__heading"><h2 id="em-title">向量模型</h2><p>用于课程资料检索，仅作用于你创建的课程；学生自动使用课程配置。</p></div>
  <p v-if="status==='loading'" class="ui-muted" role="status">正在加载向量配置…</p>
  <div v-else-if="status==='error'" class="ui-notice ui-notice--danger" role="alert"><p>向量配置加载失败，请重试。</p><button type="button" class="ui-btn" @click="load">重新加载</button></div>
  <template v-else>
   <section class="ui-config-status" aria-label="向量模型配置状态">
    <span class="ui-config-status__icon" :class="{'is-configured':configured}"><AppIcon :name="configured?'check':'key'" :size="22" /></span>
    <div class="ui-config-status__body"><h3>{{configured?'向量模型已配置':'使用系统默认向量模型'}}</h3><p data-test="em-status">{{saved?.model||'系统默认'}} · {{savedDimensions}} 维<template v-if="configured"> · 密钥 ••••{{saved?.key_hint}}</template></p></div>
   </section>
   <form class="ui-config-form" data-test="em-form" novalidate :aria-busy="busy!==null" @submit.prevent="save">
    <section class="ui-config-section" aria-labelledby="em-connection-title">
     <div class="ui-config-section__heading"><h3 id="em-connection-title">连接配置</h3><p>选择向量服务，填写 API Key 后获取模型，也可手动填写。</p></div>
     <div class="ui-field"><label for="em-provider">模型供应商</label><select id="em-provider" data-test="em-provider" :value="selectedProvider" :disabled="busy!==null" @change="chooseProvider(($event.target as HTMLSelectElement).value)"><option v-for="p in providers" :key="p.id" :value="p.id">{{p.name}}</option></select></div>
     <div class="ui-field"><label for="em-base-url">服务地址</label><input id="em-base-url" v-model="form.baseUrl" data-test="em-base-url" type="url" inputmode="url" autocomplete="off" spellcheck="false" placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1" :disabled="busy!==null" /><p>使用提供 embeddings 接口的 HTTPS 服务地址。</p></div>
     <div class="ui-field"><label for="em-api-key">API Key{{keyRequired?'':'（不改可留空）'}}</label><input id="em-api-key" v-model="form.apiKey" data-test="em-api-key" type="password" autocomplete="off" spellcheck="false" :aria-required="keyRequired" :disabled="busy!==null" /><p>密钥加密保存在服务端，保存后不再显示。</p></div>
     <div class="ui-model-directory"><button type="button" class="ui-btn" data-test="em-refresh-models" :disabled="!canDiscover||discovering||busy!==null" @click="refresh">{{discovering?'正在获取模型…':'刷新模型列表'}}</button><p v-if="discovering||discoveryMessage" class="ui-muted" role="status">{{discovering?'正在查询可用模型…':discoveryMessage}}</p></div>
     <div v-if="models.length" class="ui-field"><label for="em-model-select">可用模型</label><select id="em-model-select" data-test="em-model-select" :value="models.includes(form.model)?form.model:''" :disabled="busy!==null" @change="form.model=($event.target as HTMLSelectElement).value"><option value="" disabled>请选择向量模型</option><option v-for="name in models" :key="name" :value="name">{{name}}</option></select><p>供应商目录可能包含其他类型模型，请选择向量模型。</p></div>
     <div class="ui-field"><label for="em-model">模型名称（可手动输入）</label><input id="em-model" v-model="form.model" data-test="em-model" type="text" autocomplete="off" spellcheck="false" placeholder="例如 text-embedding-v4" :disabled="busy!==null" /></div>
     <div class="ui-field"><label for="em-dimensions">向量维度</label><select id="em-dimensions" data-test="em-dimensions" :value="dimensionChoice" :disabled="busy!==null" @change="changeDimension"><option v-for="d in dimensionOptions" :key="d" :value="String(d)">{{d}} 维</option><option value="custom">自定义维度</option></select><input v-if="customDimension" v-model.number="dimensions" data-test="em-custom-dimensions" type="number" min="1" max="4096" step="1" aria-label="自定义向量维度" :disabled="busy!==null" /><p>以模型支持的维度为准。测试会检查实际返回维度。</p><p v-if="!validDimension" class="ui-text-danger" role="alert">请输入 1–4096 的整数维度。</p></div>
    </section>
    <section class="ui-config-actions" aria-label="向量配置操作">
     <p v-if="error" class="ui-notice ui-notice--danger" data-test="em-error" role="alert">{{error}}</p>
     <p v-if="notice" class="ui-notice ui-notice--success" data-test="em-notice" role="status">向量配置已保存，课程向量已同步。</p>
     <p v-if="testResult" class="ui-notice" data-test="em-test-result" :class="testResult.ok?'ui-notice--success':'ui-notice--danger'" role="status">{{testResult.ok?'向量连接测试成功，实际返回维度与所选维度一致。':testResult.text}}</p>
     <div class="ui-actions"><button type="submit" class="ui-btn ui-btn--primary" data-test="em-save" :disabled="busy!==null||!validDimension">{{saving?'正在保存并同步课程向量…':'保存向量配置'}}</button><button type="button" class="ui-btn" data-test="em-test" :disabled="busy!==null||!validDimension" @click="test">{{testing?'正在测试…':'测试连接'}}</button></div>
     <p class="ui-muted ui-cost-hint">测试仅发送一段短文本。切换模型、地址或维度时，保存会重建你的课程向量，耗时与费用取决于资料量；失败时保留原配置。</p>
    </section>
   </form>
  </template>
 </section>
</template>
<style scoped>
.embedding-settings { margin-top:40px; padding-top:32px; border-top:1px solid var(--gw-line); }
.embedding-settings h2 { font-size:20px; margin:0; }
.embedding-settings > .ui-config-section__heading { margin-bottom:24px; }
</style>
