import { computed, onScopeDispose, ref, watch, type Ref } from 'vue'
import type { ModelConfig, ModelConfigApi } from '../api/modelConfig'
import { useRuntimeStore } from '../stores/runtime'

export const MODEL_PROVIDERS = [
  { id: 'deepseek', name: 'DeepSeek', url: 'https://api.deepseek.com' },
  { id: 'openai', name: 'OpenAI', url: 'https://api.openai.com/v1' },
  { id: 'siliconflow', name: '硅基流动', url: 'https://api.siliconflow.cn/v1' },
  { id: 'qwen', name: '阿里云百炼', url: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { id: 'custom', name: '自定义（OpenAI 兼容）', url: '' },
] as const
const TEXT: Record<string, string> = {
 auth: '密钥被拒绝，请检查 API Key 和账户权限。', unsupported: '该服务未提供兼容的模型列表。',
 timeout: '获取模型超时，请稍后刷新。', rate_limited: '请求过于频繁，请稍后刷新。',
 connection: '无法连接模型服务，请检查地址。', server: '模型服务暂时不可用。',
 malformed_response: '模型列表格式不兼容。', blocked_address: '地址不符合安全要求，请使用公网 HTTPS 地址。',
}
export function useModelDiscovery(api: ModelConfigApi, form: {baseUrl:string;apiKey:string;model:string}, saved: Ref<ModelConfig | null>) {
 const runtime = useRuntimeStore()
 const models = ref<string[]>([]), loading = ref(false), message = ref('')
 let serial = 0, controller: AbortController | null = null, timer: ReturnType<typeof setTimeout> | undefined
 const provider = computed(() => MODEL_PROVIDERS.find(p => p.url && p.url === form.baseUrl.trim().replace(/\/+$/, ''))?.id ?? 'custom')
 const canDiscover = computed(() => !!form.baseUrl.trim() && (!!form.apiKey.trim() || (saved.value?.configured === true && saved.value.base_url === form.baseUrl.trim())))
 function reset() {
  serial++;controller?.abort();controller = null;clearTimeout(timer);timer = undefined
  models.value = [];loading.value = false;message.value = ''
 }
 function chooseProvider(id:string) {
  const selected = MODEL_PROVIDERS.find(p => p.id === id)
  if (!selected || selected.id === provider.value) return
  reset();form.apiKey = '';form.model = '';form.baseUrl = selected.url
 }
 async function refresh() {
  clearTimeout(timer);timer = undefined
  if (!canDiscover.value) {message.value = '请先填写服务地址和 API Key，再获取模型。';return}
  if (!api.discover) {message.value = '模型列表暂不可用，可手动输入模型名称。';return}
  controller?.abort();const current = ++serial, owner = runtime.owner
  const active = new AbortController();controller = active;loading.value = true;message.value = '';models.value = []
  try {
   const body = {base_url:form.baseUrl.trim(),...(form.apiKey.trim() ? {api_key:form.apiKey} : {})}
   const result = await api.discover(body,{signal:active.signal,timeoutMs:20000})
   if (current !== serial || owner !== runtime.owner) return
   models.value = result.ok ? result.models : []
   message.value = result.ok ? (result.models.length ? `已获取 ${result.models.length} 个模型，可选择或手动输入。` : '没有可用模型，仍可手动输入模型名称。') : `${TEXT[result.error_class ?? ''] ?? '获取模型失败。'}可手动输入模型名称。`
  } catch {
   if (current === serial && owner === runtime.owner) message.value = '获取模型失败，请检查地址与密钥，或手动输入模型名称。'
  } finally {
   if (current === serial) {loading.value = false;controller = null}
  }
 }
 watch(() => [form.baseUrl,form.apiKey,runtime.owner], (next,previous) => {
  reset()
  // Only typing a new key starts a request; editing an address never sends the old key automatically.
  if (next[1] && next[1] !== previous[1] && next[0] === previous[0] && next[2] === previous[2]) timer = setTimeout(() => void refresh(),800)
 }, {flush:'sync'})
 onScopeDispose(reset)
 return {models,loading,message,provider,canDiscover,chooseProvider,refresh}
}
