<template>
  <div class="auth-layout auth-layout--editorial">
    <aside class="login-brand">
      <p class="login-brand__eyebrow">从资料到理解</p>
      <h1 class="login-brand__headline">把知识连起来，<br />让学习<span>有迹可循。</span></h1>
      <p class="login-brand__lede">将课程资料整理成清晰的知识图谱，<br />沿着知识之间的联系，找到自己的学习路径。</p>
      <div class="login-brand__art" data-test="login-knowledge-art" aria-hidden="true">
        <svg viewBox="0 0 660 348" aria-hidden="true" focusable="false">
          <defs>
            <pattern id="login-knowledge-dots" width="24" height="24" patternUnits="userSpaceOnUse">
              <circle cx="12" cy="12" r=".7" fill="#6f7080" opacity=".22"/>
            </pattern>
          </defs>
          <rect x="0" y="0" width="660" height="310" fill="url(#login-knowledge-dots)"/>
          <ellipse cx="333" cy="267" rx="177" ry="28" fill="none" stroke="#33343f"/>
          <ellipse cx="333" cy="267" rx="133" ry="19" fill="none" stroke="#262731"/>
          <path d="M110 201C168 201 170 255 239 249M426 248C490 248 488 193 548 193" stroke="#73708f" stroke-width="1.4" fill="none" stroke-dasharray="4 7"/>
          <g transform="translate(37 138) rotate(-8 48 50)">
            <rect x="0" y="0" width="70" height="89" rx="7" fill="#1d1f28" stroke="#55596b"/>
            <rect x="10" y="-11" width="70" height="89" rx="7" fill="#242532" stroke="#848197"/>
            <path d="M25 10h25M25 22h40M25 31h40M25 40h31" stroke="#9895af" stroke-width="2"/>
            <rect x="25" y="53" width="22" height="11" rx="3" fill="#4c456f"/>
            <text x="36" y="61" fill="#d3cafa" font-size="7" text-anchor="middle">PDF</text>
          </g>
          <g fill="none" stroke-width="1.5">
            <path d="M332 187V130M332 130 247 91M332 130 414 91M247 91 190 51M247 91 214 158M414 91 473 48M414 91 490 151" stroke="#777095"/>
            <path d="M332 130 247 91 190 51M332 130 414 91 473 48" stroke="#aaa0eb"/>
            <path d="M190 51C279 1 395 1 473 48" stroke="#393745" stroke-dasharray="3 8"/>
          </g>
          <g>
            <circle cx="190" cy="51" r="11" fill="#101114" stroke="#a99dec" stroke-width="1.7"/>
            <circle cx="190" cy="51" r="3" fill="#b1acff"/>
            <circle cx="247" cy="91" r="18" fill="#3e375d" stroke="#a89ed5"/>
            <path d="M239 87h16m-16 7h12" stroke="#d6cff7" stroke-width="1.5"/>
            <circle cx="214" cy="158" r="8" fill="#8880b6"/>
            <circle cx="332" cy="130" r="24" fill="#5b5bd6"/>
            <path d="m322 130 10-10 10 10-10 10Z" stroke="#f0ecff" stroke-width="1.5" fill="none"/>
            <circle cx="414" cy="91" r="18" fill="#3e375d" stroke="#a89ed5"/>
            <circle cx="411" cy="89" r="4" fill="none" stroke="#d6cff7" stroke-width="1.5"/>
            <path d="m414 92 6 6" stroke="#d6cff7" stroke-width="1.5"/>
            <circle cx="473" cy="48" r="11" fill="#101114" stroke="#a99dec" stroke-width="1.7"/>
            <circle cx="473" cy="48" r="3" fill="#b1acff"/>
            <circle cx="490" cy="151" r="8" fill="#8880b6"/>
          </g>
          <g font-family="Microsoft YaHei,sans-serif" font-size="11" fill="#b0a9c5">
            <text x="152" y="29">概念</text>
            <text x="223" y="66">关系</text>
            <text x="399" y="66">问答</text>
            <text x="482" y="27">路径</text>
          </g>
          <path d="M206 214 326 182 458 214 337 279Z" fill="#302b48" stroke="#7f739d"/>
          <path d="m206 214 0 14 131 64 121-63v-15L337 279Z" fill="#211e31" stroke="#5e557a"/>
          <path d="M216 197Q268 170 332 189L332 267Q279 231 216 223Z" fill="#b8ace6" stroke="#d5cafa" stroke-width="1.3"/>
          <path d="M332 189Q388 168 447 198L447 224Q383 232 332 267Z" fill="#6760b5" stroke="#b6a8e3" stroke-width="1.3"/>
          <path d="M332 189V267" stroke="#e2d7ff" stroke-width="1.6"/>
          <g stroke="#75679a" stroke-width="2" fill="none">
            <path d="M232 196q37-11 78 2M232 205q36-8 78 9M232 214q35-3 78 15"/>
          </g>
          <g stroke="#c6bbea" stroke-width="2" fill="none">
            <path d="M353 198q39-13 74-1M353 212q39-16 74-6M353 228q36-18 74-15"/>
          </g>
          <g transform="translate(555 143)">
            <path d="M0 77V52Q0 41 12 41h16q12 0 12-12V6" stroke="#a99dec" stroke-width="2" fill="none"/>
            <circle cx="0" cy="77" r="7" fill="#2b293b" stroke="#b1acff"/>
            <circle cx="28" cy="41" r="7" fill="#5b5bd6" stroke="#b1acff"/>
            <circle cx="40" cy="6" r="9" fill="#b1acff"/>
            <path d="m36 6 3 3 5-6" stroke="#302c53" stroke-width="1.6" fill="none"/>
          </g>
          <g font-family="Microsoft YaHei,sans-serif" font-size="12" fill="#c1bdcf" text-anchor="middle">
            <text x="77" y="279">课程资料</text>
            <text x="332" y="321" fill="#d4caff">知识在这里展开</text>
            <text x="578" y="279">学习路径</text>
          </g>
        </svg>
      </div>
    </aside>
    <div class="auth-layout__form"><slot /></div>
  </div>
</template>
<style scoped>
.auth-layout--editorial {
  display:grid;
  grid-template-columns:minmax(0,660px) 350px;
  gap:100px;
  align-items:center;
  width:100%;
  max-width:1216px;
  margin:0 auto;
  padding:44px 28px 58px;
  background:var(--ss-bg);
  color:var(--ss-text)
}
.login-brand {
  min-width:0
}
.login-brand__eyebrow {
  font-size:12px;
  color:var(--ss-link);
  letter-spacing:2px;
  margin:0 0 17px;
  display:flex;
  align-items:center;
  gap:10px
}
.login-brand__eyebrow::before {
  content:"";
  width:20px;
  height:2px;
  background:var(--ss-link)
}
.login-brand__headline {
  font-size:39px;
  line-height:1.45;
  letter-spacing:.4px;
  margin:0 0 16px;
  font-weight:600;
  color:var(--ss-text)
}
.login-brand__headline span {
  color:var(--ss-link)
}
.login-brand__lede {
  color:#b2b5c1;
  font-size:14px;
  line-height:1.9;
  margin:0 0 24px
}
.login-brand__art {
  width:100%;
  pointer-events:none;
  user-select:none
}
.login-brand__art svg {
  display:block;
  width:100%;
  height:auto;
  max-height:348px
}
.auth-layout__form {
  min-width:0;
  width:100%;
  padding:16px 0;
  max-height:100%;
  overscroll-behavior:contain
}
@media(max-width:1100px) {
  .auth-layout--editorial {
    grid-template-columns:minmax(0,1fr) 320px;
    gap:48px
  }
  .login-brand__headline {
    font-size:32px
  }
}
@media(max-width:760px) {
  .auth-layout--editorial {
    grid-template-columns:1fr;
    gap:0;
    padding:0 24px
  }
  .login-brand {
    display:none
  }
  .auth-layout__form {
    align-self:stretch;
    display:flex;
    align-items:safe center;
    padding:28px 0
  }
  .auth-layout__form :deep(.login) {
    width:min(100%,380px);
    margin:auto
  }
}
@media(min-width:761px) and (max-height:650px) {
  .auth-layout--editorial {
    padding-block:20px
  }
  .login-brand__headline {
    font-size:30px
  }
  .login-brand__lede {
    margin-bottom:12px
  }
  .login-brand__art svg {
    max-height:210px
  }
}
</style>
