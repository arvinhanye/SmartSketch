import { defineAsyncComponent, defineComponent, h, type Component } from 'vue'

/**
 * 路由页面按需加载。分块加载失败（网络抖动，或部署后旧分块已不存在）时自动重试，
 * 仍失败则显示可读的错误提示，而不是白屏。`maxRetries` 缺省 2 次。
 */
const loadFailed = defineComponent({
  render: () => h('p', { role: 'alert', style: 'padding:24px' }, '页面加载失败，请刷新页面重试。'),
})

export function lazyView(load: () => Promise<{ default: Component }>, maxRetries = 2): Component {
  return defineAsyncComponent({
    loader: load,
    errorComponent: loadFailed,
    onError: (_error, retry, fail, attempts) => (attempts <= maxRetries ? retry() : fail()),
  })
}
