<script setup lang="ts">
import BrandMark from './BrandMark.vue'

/**
 * 登录与注册共用的分栏封面（UI-PINE-01）：左栏白底放品牌与表单（默认插槽），右栏青松色品牌面板。
 * 背景与面板上的几何图形只作装饰，对读屏隐藏；右下角圆形徽标同样是装饰。
 */
withDefaults(defineProps<{ greeting?: string; subtitle?: string }>(), {
  greeting: '欢迎使用',
  subtitle: '登录以进入你的课程',
})
</script>

<template>
  <div class="auth-layout auth-layout--editorial">
    <div class="auth-cover__shape auth-cover__shape--disc" aria-hidden="true" />
    <div class="auth-cover__shape auth-cover__shape--blob" aria-hidden="true" />
    <div class="auth-cover__shape auth-cover__shape--pill" aria-hidden="true" />
    <div class="auth-cover__shape auth-cover__shape--ring" aria-hidden="true" />

    <div class="auth-cover">
      <div class="auth-cover__panel">
        <div class="auth-cover__brand">
          <BrandMark :size="40" />
          <span class="auth-cover__name">智绘学途<small>SmartSketch</small></span>
        </div>
        <div class="auth-layout__form"><slot /></div>
      </div>

      <aside class="login-brand">
        <svg class="login-brand__art" data-test="login-knowledge-art" viewBox="0 0 620 580" preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false">
          <circle cx="580" cy="20" r="190" fill="#127d6b" />
          <circle cx="580" cy="20" r="128" fill="none" stroke="#5fc3a8" stroke-width="2" opacity=".55" />
          <circle cx="580" cy="20" r="250" fill="none" stroke="#1a8774" stroke-width="1.5" />
          <rect x="-110" y="-60" width="300" height="130" rx="65" fill="#f5b82e" transform="rotate(-24 40 5)" />
          <rect x="150" y="70" width="170" height="44" rx="22" fill="#5fc3a8" opacity=".85" transform="rotate(-24 235 92)" />
          <path d="M120 140 230 30" stroke="#fff" stroke-width="2" stroke-linecap="round" opacity=".35" />
          <g fill="#5fc3a8" opacity=".6">
            <circle cx="404" cy="150" r="2.5" /><circle cx="422" cy="150" r="2.5" /><circle cx="440" cy="150" r="2.5" /><circle cx="458" cy="150" r="2.5" />
            <circle cx="404" cy="168" r="2.5" /><circle cx="422" cy="168" r="2.5" /><circle cx="440" cy="168" r="2.5" /><circle cx="458" cy="168" r="2.5" />
            <circle cx="404" cy="186" r="2.5" /><circle cx="422" cy="186" r="2.5" /><circle cx="440" cy="186" r="2.5" /><circle cx="458" cy="186" r="2.5" />
          </g>
          <circle cx="-40" cy="300" r="110" fill="none" stroke="#127d6b" stroke-width="22" />
          <circle cx="130" cy="660" r="230" fill="none" stroke="#0b5d50" stroke-width="44" />
          <path d="M30 620V510a40 40 0 0 1 40-40h230a40 40 0 0 0 40-40v-18" fill="none" stroke="#f5b82e" stroke-width="12" stroke-linecap="round" stroke-linejoin="round" />
          <circle cx="340" cy="402" r="11" fill="#0e6b5c" stroke="#fff" stroke-width="3" />
          <path d="M352 402h168a30 30 0 0 0 30-30V170a30 30 0 0 1 30-30h60" fill="none" stroke="#d8efe8" stroke-width="3" stroke-dasharray=".5 10" stroke-linecap="round" />
          <circle cx="550" cy="290" r="8" fill="#f5b82e" />
          <rect x="560" y="250" width="150" height="54" rx="27" fill="#fff" opacity=".1" transform="rotate(-45 635 277)" />
          <path d="M400 640 560 480" stroke="#5fc3a8" stroke-width="14" stroke-linecap="round" opacity=".7" />
          <path d="M470 640 650 460" stroke="#0f3d36" stroke-width="6" stroke-linecap="round" />
          <path d="M500 500 548 452" stroke="#f5b82e" stroke-width="14" stroke-linecap="round" />
          <path d="M200 560h60" stroke="#fff" stroke-width="3" stroke-linecap="round" opacity=".45" />
        </svg>
        <div class="login-brand__text">
          <p class="login-brand__headline">{{ greeting }} <strong>智绘学途</strong></p>
          <p class="login-brand__lede">{{ subtitle }}</p>
        </div>
      </aside>

      <div class="auth-cover__badge" aria-hidden="true">
        <svg viewBox="0 0 84 84" width="84" height="84" focusable="false">
          <path d="M38 62 68 26" fill="none" stroke="#0e6b5c" stroke-width="14" stroke-linecap="round" />
          <path d="M18 44 38 62" fill="none" stroke="#f5b82e" stroke-width="14" stroke-linecap="round" />
        </svg>
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth-layout--editorial {
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 100%;
  padding: 48px;
  background: var(--ui-bg);
  color: var(--ui-text);
}
.auth-cover__shape {
  position: absolute;
  pointer-events: none;
}
.auth-cover__shape--disc {
  width: 640px;
  height: 640px;
  right: -170px;
  top: -250px;
  border-radius: 50%;
  background: var(--ui-brand);
}
.auth-cover__shape--blob {
  width: 440px;
  height: 440px;
  left: -150px;
  bottom: -200px;
  border-radius: 46% 54% 60% 40% / 50% 42% 58% 50%;
  background: var(--ui-highlight);
}
.auth-cover__shape--pill {
  width: 220px;
  height: 60px;
  right: 90px;
  bottom: 70px;
  border-radius: 30px;
  background: var(--ui-mint);
  transform: rotate(-32deg);
}
.auth-cover__shape--ring {
  width: 120px;
  height: 120px;
  left: 160px;
  top: 40px;
  border-radius: 50%;
  border: 10px solid var(--ui-primary);
}
.auth-cover {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: minmax(320px, 400px) minmax(0, 1fr);
  width: 100%;
  max-width: 1040px;
  height: min(580px, calc(100dvh - 96px));
  min-height: 460px;
  border-radius: 6px;
  box-shadow: 0 30px 70px rgb(15 61 54 / 24%);
}
.auth-cover__panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 36px 48px 28px;
  border-radius: 6px 0 0 6px;
  background: var(--ui-surface);
}
.auth-cover__brand {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: none;
}
.auth-cover__name {
  display: flex;
  flex-direction: column;
  font-size: 17px;
  font-weight: 700;
  line-height: 1.15;
  letter-spacing: .04em;
  color: var(--ui-text);
}
.auth-cover__name small {
  font-size: 11px;
  font-weight: 500;
  letter-spacing: .06em;
  color: var(--ui-text-2);
}
.auth-layout__form {
  flex: 1;
  min-width: 0;
  width: 100%;
  /* 表单栏只留小边距：窗口一矮就靠内部滚动，不出现整页滚动条。 */
  padding: 8px 0;
  max-height: 100%;
  overscroll-behavior: contain;
  display: flex;
  flex-direction: column;
}
.login-brand {
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-width: 0;
  padding: 64px 72px;
  border-radius: 0 6px 6px 0;
  background: var(--ui-primary);
  color: #fff;
}
.login-brand__art {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  user-select: none;
}
.login-brand__text {
  position: relative;
}
.login-brand__headline {
  margin: 0 0 14px;
  font-size: 44px;
  font-weight: 300;
  line-height: 1.2;
  letter-spacing: .02em;
}
.login-brand__headline strong {
  font-weight: 700;
}
.login-brand__lede {
  margin: 0;
  font-size: 18px;
  font-weight: 300;
  color: #d8efe8;
}
.auth-cover__badge {
  position: absolute;
  right: -54px;
  bottom: -58px;
  display: grid;
  place-items: center;
  width: 156px;
  height: 156px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 18px 40px rgb(15 61 54 / 20%);
}
@media (max-width: 1100px) {
  .auth-cover__badge { display: none; }
  .login-brand { padding: 48px; }
  .login-brand__headline { font-size: 36px; }
}
@media (max-width: 860px) {
  .auth-layout--editorial { padding: 24px 16px; align-items: flex-start; }
  .auth-cover { grid-template-columns: minmax(0, 1fr); height: auto; min-height: 0; }
  .auth-cover__panel { border-radius: 6px 6px 0 0; padding: 28px 24px; }
  .login-brand { order: -1; min-height: 160px; padding: 32px 24px; border-radius: 6px 6px 0 0; }
  .auth-cover__panel { order: 0; border-radius: 0 0 6px 6px; }
  .login-brand__headline { font-size: 28px; }
  .login-brand__lede { font-size: 15px; }
  .auth-cover__shape--pill, .auth-cover__shape--ring { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .auth-cover * { transition: none !important; }
}
</style>
