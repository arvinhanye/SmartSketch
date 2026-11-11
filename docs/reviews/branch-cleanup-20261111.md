# 分支清理核查（2026-11-11）

基线 `origin/main@99e169af9cbb42b696a610bc785c1fb2fd94c93a`；195 个远端分支、20 个本地分支。删除只涉及引用，不删除工作区文件。

恢复备份：主检出目录 `.demo/branch-cleanup-20261111/all-branches.bundle`（完整历史，`git bundle verify` 通过）；原始清单和操作日志同目录。已进入 main 的提交可直接按下表 SHA 恢复；其他历史提交可从 bundle 恢复。

## 远端引用处置

`ancestor` 表示完整提交历史已包含；`git cherry` 表示所有非合并补丁已有等价提交；`same tree` 表示与 main 的文件树完全一致。保留项的独有内容未经本轮验收，不强行合入，也不删除。

| 分支 | 原 SHA | 处置 | 依据 |
| --- | --- | --- | --- |
| `B06` | `ca6c405d926d9b002c4d78b2b4a6de80e361f246` | 删除 | ancestor of origin/main@99e169a |
| `claude/a08-signoff` | `8f1e73f188e7b01301574b7a0a8e6dbe3f135ee2` | 删除 | ancestor of origin/main@99e169a |
| `claude/a09-dev-environment-check-8e5e93` | `19d2079294f939f396b476f64177fed8c755e66c` | 删除 | ancestor of origin/main@99e169a |
| `claude/a1-a10-meta-task-wrap-ddbf4b` | `b20a1078ba70cc883601440378d1341db87295bf` | 删除 | ancestor of origin/main@99e169a |
| `claude/a10-integration-map` | `4017f70c3b2da2efb07ea4f9627582c77b4ed998` | 删除 | ancestor of origin/main@99e169a |
| `claude/a10-r01-r02-fix` | `e0adf247bfbc379b0303d2ca4777feaa7cf184f0` | 删除 | ancestor of origin/main@99e169a |
| `claude/adr-012-r3` | `b15019a7772d87db1d0583044b0dcb93648d6536` | 删除 | ancestor of origin/main@99e169a |
| `claude/adr-017-decisions` | `d446ecce0ed450b0830cd7fcd3536f729dcf7d2c` | 删除 | ancestor of origin/main@99e169a |
| `claude/archive-codex-reviews` | `a8e917cee0b132490639cde469e8f621dda9dacc` | 删除 | ancestor of origin/main@99e169a |
| `claude/b03-b04` | `a783fe2e424ca9c314de7718b446fa291dc8e6c8` | 删除 | ancestor of origin/main@99e169a |
| `claude/b03-b04-prep` | `9dddcb4ea18e074fdfd1476823b48b0832231252` | 删除 | ancestor of origin/main@99e169a |
| `claude/b10-task-sse-contract` | `94008b2032a2e2ddec928c173ea775e195d88911` | 删除 | ancestor of origin/main@99e169a |
| `claude/b11-closeout` | `bd08d192dc5d694632731f22d5b8778dc3ec3049` | 删除 | ancestor of origin/main@99e169a |
| `claude/b12-progress-contract` | `56660b2d369a356c3f4cf1434c91969cab8b0022` | 删除 | ancestor of origin/main@99e169a |
| `claude/b12-r1-progress-errors` | `a4f08ca6227ab09830c3f943827ccee1b0de4477` | 删除 | ancestor of origin/main@99e169a |
| `claude/b13-chat-contract` | `8a4992cf7e05ae8420a2f3f7d5dc492f2cc76ac1` | 删除 | ancestor of origin/main@99e169a |
| `claude/b13-r09` | `743ece9ba9a7278da1aabe1143a2479e9d4fb527` | 删除 | ancestor of origin/main@99e169a |
| `claude/b15-http-client` | `03072500951b8810c3feac5413ac4c1a059f6de2` | 删除 | ancestor of origin/main@99e169a |
| `claude/batch-0925-claims` | `38ef62d2db098347ffa3b8880f0720920096621a` | 删除 | ancestor of origin/main@99e169a |
| `claude/batch-0925-closeout` | `2c32030e17f8f15999ca79a8f293880e2adfd363` | 删除 | ancestor of origin/main@99e169a |
| `claude/batch-0925b-claims` | `6a93cf3c6d6a69dd4c26fc03e9e6d9b0c35466b6` | 删除 | ancestor of origin/main@99e169a |
| `claude/batch-0925c-claims` | `9116315f083028d12969af37a98a839f7558fe76` | 删除 | ancestor of origin/main@99e169a |
| `claude/batch-0925d-claims` | `71600b2a9c90731411f4ad2516d4d8bd3f3281b7` | 删除 | ancestor of origin/main@99e169a |
| `claude/batch-0925e-claims` | `f0814cc856b3c91e6d96e73eab25020e3dfa804b` | 删除 | ancestor of origin/main@99e169a |
| `claude/batch-0925f-closeout` | `9d04997210ae1d61838250a2c0a8bc5fff001918` | 删除 | ancestor of origin/main@99e169a |
| `claude/batch-status-0924` | `f4b42cd0f2daa02ab6c188da3853964af8f0cc1e` | 删除 | ancestor of origin/main@99e169a |
| `claude/batch1-grounded-qa` | `dc9443efd55b59c5a576f13a1ca288e24599e5ff` | 删除 | ancestor of origin/main@99e169a |
| `claude/batch7-claim` | `85adfa70a718fc28cf9d9dc8c6decec7c62d4f32` | 删除 | ancestor of origin/main@99e169a |
| `claude/batch8-claim` | `bdcf1651c802b4748b3bbcc5be3a3320f57b2491` | 删除 | ancestor of origin/main@99e169a |
| `claude/board-0925-codex-closeout` | `42e05524daefa56e2a9839dee0da03841203bea3` | 删除 | ancestor of origin/main@99e169a |
| `claude/board-review-closeout` | `681e618216bb3b033816c3b2c057176c22a5b2a6` | 删除 | ancestor of origin/main@99e169a |
| `claude/c02-course-repo` | `96cd00dab4d4dee33810cef3d60596c2a49e4aac` | 删除 | ancestor of origin/main@99e169a |
| `claude/c05-file-storage` | `d3b7a6ca394ca7296d97b7019cc2c12500baf529` | 删除 | ancestor of origin/main@99e169a |
| `claude/c07-materials-api` | `8311414cecac396c860dcc0a1d6a5a6ae2afbdd1` | 删除 | ancestor of origin/main@99e169a |
| `claude/c08-done` | `c1de109bb0a678852ef261fae93265edf705df5e` | 删除 | ancestor of origin/main@99e169a |
| `claude/c09-task-leases` | `b8afa590ecea038bfb4b7631421195a89d59b1f5` | 删除 | ancestor of origin/main@99e169a |
| `claude/c10-task-cancel` | `41849ba5a3337047281e0c73cb54e23926e7cc75` | 删除 | ancestor of origin/main@99e169a |
| `claude/c11-task-events` | `eac84644e0c504afa4eaeddb586d4f330f9d32d3` | 删除 | ancestor of origin/main@99e169a |
| `claude/c12-task-stream` | `52dcf95a574b03896ca3ff8a2ce4ea2326e60f49` | 删除 | ancestor of origin/main@99e169a |
| `claude/c13-auth` | `da4dcc17ae445726a900d08bffbda7e311d5467f` | 删除 | ancestor of origin/main@99e169a |
| `claude/c13-d01-board` | `4f93f1dd1c20f1cc42588d878400db71e57e8925` | 删除 | ancestor of origin/main@99e169a |
| `claude/c14-account-seed` | `1811750272994e6be1fe76b5294ae743966299e7` | 删除 | ancestor of origin/main@99e169a |
| `claude/c15-course-members` | `ea3a1b34fc8f0b6f00aa12637b1a4ffaebf16187` | 删除 | ancestor of origin/main@99e169a |
| `claude/c16-event-tickets` | `0478ae561e3d585645870409fbff6e6209fc4cc2` | 删除 | ancestor of origin/main@99e169a |
| `claude/check-pending-prs-tasks-1ba7fe` | `79ba1bfb9e64b6ac99da97c299c777e7bcb12787` | 保留 | unique work; not proven redundant |
| `claude/ci-02` | `0040655473a785a815f378004121abc0e2e8c6fb` | 删除 | ancestor of origin/main@99e169a |
| `claude/claim-d02-d05` | `2c3edf4c78b1ae534cc0f511e8406fecdbbf69c8` | 删除 | ancestor of origin/main@99e169a |
| `claude/clever-dirac-y8fng3` | `3f6edda2d8cbca7ac4907061c84360e2ec6d8105` | 删除 | ancestor of retained claude/impl-k09 |
| `claude/code-structure-review-handoff-49e73a` | `2675a44c2b6a9c0de0a68c29de07a5b5c7793341` | 删除 | same tree as origin/main@99e169a; PR #337 redundant |
| `claude/codex-a08-check-ade85c` | `acb257cf03d094bf0ccc4eac2610e001b17fd2d6` | 删除 | ancestor of origin/main@99e169a |
| `claude/codex-handoff-0924` | `b60fe9c93c2b6f5717d529ac5d59f00808a2b300` | 删除 | ancestor of origin/main@99e169a |
| `claude/d01-parse-model` | `74be60de24f797796bfe648ccd288c91be75a0b0` | 删除 | ancestor of origin/main@99e169a |
| `claude/d02-done-decisions` | `7034b41db690ca285ccc530d65380b408495e195` | 删除 | ancestor of origin/main@99e169a |
| `claude/d02-txt-parser` | `465170080d4c4381b6342900750dbdfe50b84255` | 删除 | ancestor of origin/main@99e169a |
| `claude/d03-markdown-parser` | `0e4e29242cb282fa46aa2a3d78003189b972c625` | 删除 | ancestor of origin/main@99e169a |
| `claude/d04-docx-parser` | `c7b2b7683d5bc9dd6db258105df11f00a6b9545e` | 删除 | ancestor of origin/main@99e169a |
| `claude/d05-pdf-parser` | `93d5971764ca3bcaccf472ccd9bc986de4a44a98` | 删除 | ancestor of origin/main@99e169a |
| `claude/d06-pdf-headings` | `516b58892118d433bdf97d50c282da98943aba60` | 删除 | ancestor of origin/main@99e169a |
| `claude/d07-header-footer` | `ded16d1f2e9af251e3856f802ef1e56d7cdfa9fd` | 删除 | ancestor of origin/main@99e169a |
| `claude/d09-chunk-identity` | `410a7e3683172a4cde8c8c7e44b092355edd31a9` | 删除 | ancestor of origin/main@99e169a |
| `claude/d10-chunk-store` | `5321bd0c050623d1513d5907a7d324d1063b61f6` | 删除 | ancestor of origin/main@99e169a |
| `claude/d11-e08-c11-j03-claim-30f32f` | `6c50d2cded895fbbc4d5fd4f8d560473649a1409` | 删除 | ancestor of origin/main@99e169a |
| `claude/d11-parse-worker` | `4f2b316a54d1325dd2caf5ae3cf0aa0916767afb` | 删除 | ancestor of origin/main@99e169a |
| `claude/d11-upload-config` | `560cd375fd717a5c3890da24ae2b58ad5626add1` | 删除 | ancestor of origin/main@99e169a |
| `claude/e01-prompts` | `907c2fae033c53215649d6d21bb08a5d79010fd0` | 删除 | ancestor of origin/main@99e169a |
| `claude/e02-ai-client` | `59d16613e4c6e04fea84e5a26a6a9ea121eb0620` | 删除 | ancestor of origin/main@99e169a |
| `claude/e03-compatible-api` | `5f983499ae61878964f6a93e77da60a8365a27cd` | 删除 | ancestor of origin/main@99e169a |
| `claude/e04-call-policy` | `7d1f07686dd988e9fce7dd84587be1bbdd1eb5fd` | 删除 | ancestor of origin/main@99e169a |
| `claude/e05-entity-extraction` | `917eb94588b05a2659a52a3419ac5b11b56d046e` | 删除 | ancestor of origin/main@99e169a |
| `claude/e06-gleaning` | `1b383c1a6cbce44da4bb2b110f4f80a92ea2f71e` | 删除 | ancestor of origin/main@99e169a |
| `claude/e08-name-normalize` | `c6cb07745c2ad740c1fc5ebd6e170832f50ba474` | 删除 | ancestor of origin/main@99e169a |
| `claude/e09-vector-tiers` | `92dcde9e4e7cf02c8b2fcf8ec12cff0c48172d9b` | 删除 | ancestor of origin/main@99e169a |
| `claude/f01-neo4j-env` | `d6bec11c4f5ee64e78a1292e8c8ae324ee9bd53c` | 删除 | ancestor of origin/main@99e169a |
| `claude/f05-dag-cycle` | `2cbe52615fb928e81d2b4416253e057ca442b7e2` | 删除 | ancestor of origin/main@99e169a |
| `claude/fix-migrate-lease-guard` | `cf284c1d0e0f917dce4dd4f502e3e1bb383822b4` | 删除 | ancestor of origin/main@99e169a |
| `claude/fix-r01-r02` | `8dcd7b2533a4111c3f169704931635e5c6ef0177` | 删除 | ancestor of origin/main@99e169a |
| `claude/frontend-dev-04eee7` | `f4b3054b74bf31c4faa233a3716a7d4caaaa43c3` | 删除 | ancestor of origin/main@99e169a |
| `claude/frontend-polish-batch3` | `08443b4c87d9753abf64b4767dbf30fd2f3742d0` | 删除 | ancestor of origin/main@99e169a |
| `claude/frontend-redesign-vzvfus` | `65abb4cde69652dbfb3c4dd4a409cb0dbc9a2533` | 删除 | ancestor of origin/main@99e169a |
| `claude/h01-courses-view` | `a0bbd10bd7657f9a976baa2bd528a46cd8a855c6` | 删除 | ancestor of origin/main@99e169a |
| `claude/h13-login-session` | `ec19af781a0af40b4b651790f20a9caafd81c594` | 删除 | ancestor of origin/main@99e169a |
| `claude/i03-eligible-set` | `84501c88263f14938ae4fdb931e530de359638aa` | 删除 | ancestor of origin/main@99e169a |
| `claude/i04-ranking` | `637f0b9b7e60c75f24d85f669bff55a9a90e6be7` | 删除 | ancestor of origin/main@99e169a |
| `claude/impl-i06` | `244664797be2cbf939f7b6ef9f23dcc16f29ba73` | 删除 | ancestor of origin/main@99e169a |
| `claude/impl-j08` | `02357d78de7d9986fdb54ad50d662684868d7cea` | 保留 | unique work; not proven redundant |
| `claude/impl-k09` | `8eb9b9f27fdb5ab07e1a70cd5b4629f9efdcee66` | 保留 | unique work; not proven redundant |
| `claude/integration-0926` | `5d9efee82f9ce25bf5e3ca8238da68a060b4c983` | 删除 | ancestor of origin/main@99e169a |
| `claude/integration-0927` | `3ea7cca06b3e86d9a2ddfa9ddf55685db498a763` | 删除 | ancestor of origin/main@99e169a |
| `claude/j03-query-rewrite` | `616d758604f3f3d693404aad4e75e594bc0c0531` | 删除 | ancestor of origin/main@99e169a |
| `claude/k14-prompt-record` | `8f11b39c5e733b9eabd40b6e531bc6826af19f90` | 删除 | ancestor of origin/main@99e169a |
| `claude/knowledge-graph-ux-analysis-2e7400` | `983dcba0009abbbf56394771ebe361768dfae768` | 删除 | integrated through PR #343; PR #342 merged |
| `claude/laughing-ptolemy-4x1c7g` | `4ca834058de73c9ebad1fadc73ec99dce5b5115c` | 保留 | unique work; not proven redundant |
| `claude/launcher-upgrade-fix` | `14fd1ee9bd2476c5c83c9a22a077552b4fc9eee1` | 删除 | ancestor of origin/main@99e169a |
| `claude/migration-numbering` | `9f21e0737aafd24966dbee92438dd15fe1e0a8af` | 删除 | ancestor of origin/main@99e169a |
| `claude/multi-agent-contract-format-209be9` | `bef9b910db3e804815daa378384d1d7a65a52d6c` | 删除 | ancestor of retained claude/worktree-contract-conflicts-740adb |
| `claude/one-click-start-2ibfrb` | `31f15c2155c58a2a16513788f29ac610813e814f` | 删除 | ancestor of origin/main@99e169a |
| `claude/opt01-06-review-submit-598cc3` | `030408e80609107ee37f7585cfa374c42af1037a` | 删除 | ancestor of origin/main@99e169a |
| `claude/parsers-batch-done` | `5b6fa01af16d50f99f15e8f4ace87212ac04e165` | 删除 | ancestor of origin/main@99e169a |
| `claude/pdf-course-model-training-0b0f46` | `2f1d3d621417945cb9b0a3bf2dbe2c5777868c8b` | 删除 | ancestor of origin/main@99e169a |
| `claude/pdf-parser-version-tech-debt-e95eaf` | `419cd7434e731ec27d1742e22784c2699ea60981` | 删除 | ancestor of origin/main@99e169a |
| `claude/plan-c-acceptance` | `bbc8fbea8789305f0e1bec07fa0da9d9e2cfbe3b` | 删除 | ancestor of origin/main@99e169a |
| `claude/project-thread-130wun` | `9adf0b3a4cae0afef4e2af233e985a4a871a74f6` | 删除 | all patches already integrated (git cherry) |
| `claude/project-thread-200r6n` | `2bb305c4d665ddd261141bcade480b28ab05f6dc` | 删除 | ancestor of origin/main@99e169a |
| `claude/project-thread-21sjlj` | `40c0c895beca5befa8db343faeb866a96e089caa` | 删除 | ancestor of origin/main@99e169a |
| `claude/project-thread-3eixq2` | `1d6369669f46587acfdcb187fb0b190869b80c7f` | 删除 | ancestor of origin/main@99e169a |
| `claude/project-thread-8wzxew` | `c1af79e9601d1180a9e34a6275293fa6603f7dcb` | 删除 | ancestor of origin/main@99e169a |
| `claude/project-thread-98kaqt` | `00e3cd161954e0034ad3b8b6cb01d15a02606d89` | 删除 | ancestor of origin/main@99e169a |
| `claude/project-thread-9f2hs5` | `bb02f93fc841ade12927528ec573e3f1d6eb8cef` | 删除 | ancestor of origin/main@99e169a |
| `claude/project-thread-bd1f83` | `0fb0cb7de50d2c196288701dcb7d716f562f56ac` | 删除 | ancestor of origin/main@99e169a |
| `claude/project-thread-bkxc2u` | `657bf44d116b62b179df6c1ba409d30a36754f06` | 删除 | ancestor of origin/main@99e169a |
| `claude/project-thread-cd4etm` | `1598b6563419ecbdd5dd9e376490acea20ecc083` | 删除 | ancestor of origin/main@99e169a |
| `claude/project-thread-diyack` | `284f5b9b4eda91b7c5f2754ac1d75a6038cba85b` | 删除 | ancestor of origin/main@99e169a |
| `claude/project-thread-eo5fzo` | `61bc8c94ac65324890f420255e69f1fdf540e88e` | 删除 | ancestor of origin/main@99e169a |
| `claude/project-thread-fqm6l4` | `b1f80d975333ada64d17df52d98baecb0551e6d9` | 删除 | ancestor of origin/main@99e169a |
| `claude/project-thread-m4mk7n` | `dbae388a7c8b74e2979ef5bc85e5a8d59ff70085` | 删除 | ancestor of origin/main@99e169a |
| `claude/project-thread-n5wcl5` | `d93ec4666e03da3da72bb4983c13da31095b4fcd` | 删除 | ancestor of origin/main@99e169a |
| `claude/project-thread-ohmwyv` | `222e2914b3d397f4135ad00266bb8fb623783b37` | 删除 | all patches already integrated (git cherry) |
| `claude/project-thread-sa7c37` | `1aaf2b0505ed32508515d982e55b53b82a0732f9` | 删除 | ancestor of origin/main@99e169a |
| `claude/project-thread-sp1d3a` | `130146ef1dbf477dd490ac2945bfa9d6d33f651a` | 删除 | ancestor of origin/main@99e169a |
| `claude/project-thread-sqwla4` | `0ab720be27bec3aeeb37111beb34db671ebd9b5c` | 删除 | ancestor of origin/main@99e169a |
| `claude/project-thread-vrtfxt` | `d0a491a7c5f06df22867e67849788f1f240aac29` | 删除 | all patches already integrated (git cherry) |
| `claude/project-thread-yswyz2` | `8ee2cbf9b02e28cd115c8e9f4c88d09080905196` | 删除 | ancestor of origin/main@99e169a |
| `claude/project-thread-z0m8yg` | `68a75153cd1cf730c1de5a69c214e94486863853` | 删除 | ancestor of origin/main@99e169a |
| `claude/quirky-dijkstra-eca5de` | `05d214c09b770b0a18268f5e1ee27bb5194bc1dd` | 删除 | ancestor of origin/main@99e169a |
| `claude/readme-published` | `0256caa5b1b4a721408af9e361bc508091d37fd3` | 删除 | ancestor of origin/main@99e169a |
| `claude/real-model-setup-zxgnka` | `fd31920005c8ed8a8eba7551c3342eb331839c9a` | 删除 | ancestor of origin/main@99e169a |
| `claude/register-layout` | `aa9b762e82366eedcdce66cb14f1c595ddd72b4a` | 删除 | ancestor of origin/main@99e169a |
| `claude/release-closeout` | `687ae143bd935fcaf7e0896d62bdf6647e8b2745` | 删除 | ancestor of origin/main@99e169a |
| `claude/release-launcher-merge` | `a57623710f2ac1145e7228bd8ab278cc8c0c4013` | 删除 | ancestor of origin/main@99e169a |
| `claude/release-rc-7f8a0cd` | `3d5f6a7bb55fd8023dc25cb233710a68c0a6ffe5` | 删除 | ancestor of origin/main@99e169a |
| `claude/smartsketch-contest-sprint-77644f` | `68762e8ab9efdfc20552a94668d7e26deb2e34c5` | 删除 | ancestor of origin/main@99e169a |
| `claude/smartsketch-frontend-init-0d2af9` | `ab601831791da40345f74d515652a7315dd63429` | 删除 | ancestor of origin/main@99e169a |
| `claude/td02-task-repo` | `b477cc695854867ce6895ab837b2657fb8d03ed8` | 删除 | ancestor of origin/main@99e169a |
| `claude/teacher-graph-legend` | `e0b67cdfc168c5c5883152048c7a7693afafdd21` | 删除 | ancestor of origin/main@99e169a |
| `claude/tech-plan-review-improvements-ff30e0` | `6ccbe5e80851f9d05897c2a9093a5f6dc8dfd23d` | 删除 | ancestor of retained claude/worktree-contract-conflicts-740adb |
| `claude/ui-baseline-0927` | `88e94e0f8089903ef4380e7e69f6808e496f11c7` | 删除 | ancestor of origin/main@99e169a |
| `claude/ui-batch2-01` | `f54484d6684a0add23b46bb0e2db2550fbdd8648` | 删除 | ancestor of origin/main@99e169a |
| `claude/ui-qa-01-chat-chain` | `fb93b931b5831245f1e0d48da14e80dd38c2403b` | 删除 | ancestor of origin/main@99e169a |
| `claude/ui-rail-and-toast` | `9d1aa159453b0a9f3fd44f341b0ef5dbad9fec0d` | 删除 | ancestor of origin/main@99e169a |
| `claude/ui-rollout-batch2-plan` | `55b19d0da324d1ac56280e493f828d8b56e4bb23` | 删除 | ancestor of origin/main@99e169a |
| `claude/upbeat-ramanujan-p4ccbq` | `64df33cdc385076fc1feeaed65dfa1cd9739d999` | 删除 | ancestor of origin/main@99e169a |
| `claude/worktree-contract-conflicts-740adb` | `978671eecd16176ad880e03e3efee4839c1e89d7` | 保留 | unique work; not proven redundant |
| `claude/worktree-meaning-7a61bc` | `05d214c09b770b0a18268f5e1ee27bb5194bc1dd` | 删除 | ancestor of origin/main@99e169a |
| `codex/a08-learning-path` | `31756b22653b6ff68a4d8a22faccc9b5b99343c5` | 删除 | ancestor of origin/main@99e169a |
| `codex/api-settings` | `90fe0e44bfee457d0f8279d7531ef67a42e86477` | 删除 | ancestor of retained frontend-ui-revision |
| `codex/auth-graph-motion-20260928` | `93d45bdd1d73b0238b41c432f4324533a30ad193` | 删除 | ancestor of origin/main@99e169a |
| `codex/b01-vue-scaffold` | `a7dfad360c0b215b4682f3dd5ec0dbe495ba99f9` | 删除 | ancestor of origin/main@99e169a |
| `codex/b05-fastapi-health-github` | `148fa9fd23085b2c9301a6ebb84d598f803190e7` | 删除 | ancestor of origin/main@99e169a |
| `codex/b07-closeout` | `b07358ab52a8e661496cc4d93accc61265b52969` | 删除 | ancestor of origin/main@99e169a |
| `codex/b07-contract-gate` | `9c7bf78a23b0d9cf7b129aa34b5ae3972db883ec` | 删除 | ancestor of origin/main@99e169a |
| `codex/b11-graph-contract` | `921a451d05b8106966af6e7677f3342848856818` | 删除 | ancestor of origin/main@99e169a |
| `codex/b14-contract-drift` | `fc1b8ad1f82d0f31036c2396a7a8af03ef24e0de` | 删除 | ancestor of origin/main@99e169a |
| `codex/c01-sqlite` | `c1c48aa5d8de3340de0704ac3bc489ea4b696084` | 删除 | ancestor of origin/main@99e169a |
| `codex/c03-access-boundary` | `dd646aa26e6f784387855953c29965434cc3eaa4` | 删除 | ancestor of origin/main@99e169a |
| `codex/c04-courses-api` | `e691d5fb50cdc7eaa443037519fbd383cc20a769` | 删除 | ancestor of origin/main@99e169a |
| `codex/c06-material-task-transaction` | `1ed73d5268b63512554c36f78ac86cdd6f4224eb` | 删除 | ancestor of origin/main@99e169a |
| `codex/c08-task-state` | `e23e6d5294648779bec713a83d25a2fcf04a1f09` | 删除 | ancestor of origin/main@99e169a |
| `codex/d08-semantic-chunking` | `cd88a1d946935b38af2e5df6430fc760f8346428` | 删除 | ancestor of origin/main@99e169a |
| `codex/e07-embedding-adapter` | `f732baa0b70066fb7d0e877062c88134a9a6ac86` | 删除 | ancestor of origin/main@99e169a |
| `codex/e10-fusion-design` | `cbafe9caa952ef4e9bde5189b431604c94853c3b` | 删除 | ancestor of origin/main@99e169a |
| `codex/enum-input-validation` | `6d21fdeb49bf8352896b00ec48398e52b5c8488b` | 删除 | ancestor of origin/main@99e169a |
| `codex/f02-neo4j` | `39ce08e7b653c335bdec08737eb75d6b329066fc` | 删除 | ancestor of origin/main@99e169a |
| `codex/f03-graph-migrations` | `e4374a2998ac2bcf57a99698295eda7105cc2ff5` | 删除 | ancestor of origin/main@99e169a |
| `codex/h09-i05-closeout` | `4162306eaa08f8ddebe39569dc8a062cdf012305` | 删除 | ancestor of origin/main@99e169a |
| `codex/h10-version-panel` | `f3871d62655db91ab9caa113619eed390af35f19` | 删除 | ancestor of origin/main@99e169a |
| `codex/i01-review-fix` | `8ccaa79479663a50d6396cd556e295e2b3a5ed07` | 删除 | ancestor of origin/main@99e169a |
| `codex/j02-graph-search` | `aec5045eaa0e48d75a2037e62e1d544b311d9b16` | 保留 | unique work; not proven redundant |
| `codex/j06-citation-review` | `1e10985b343939ef1f62e364ca17c4bc9a5a6b82` | 删除 | ancestor of origin/main@99e169a |
| `codex/j07-chat-api` | `7e31d3336a1ec4da7c4110e1b198c785cde90369` | 删除 | ancestor of origin/main@99e169a |
| `codex/j08-chat-stream` | `3303cefcb9930246d1e4eb21d04b138faf7643e0` | 保留 | unique work; not proven redundant |
| `codex/j08-review-fix` | `fc4876ac8ed9dbeaffbbb72ca37b2c917eb75240` | 删除 | ancestor of origin/main@99e169a |
| `codex/j09-chat-page` | `aa5518f07bbe6e5406a423dc7ccb9d859fb8a62d` | 删除 | ancestor of origin/main@99e169a |
| `codex/j10-chat-logs` | `17513b8b3c39416b92780377a917290e2abc9ac5` | 删除 | ancestor of origin/main@99e169a |
| `codex/k03-qa-evaluation` | `21c9412ca8da54ca9da9fe3c6b34fd5fe58a10d1` | 删除 | ancestor of origin/main@99e169a |
| `codex/k04-benchmark-pipeline` | `18db112b8c3ac076b258f7b6a4c64dea2551b1d1` | 删除 | ancestor of origin/main@99e169a |
| `codex/k05-teacher-e2e` | `442daf7384efb17e0a54a9fcc0e8e5aa4068af50` | 保留 | unique work; not proven redundant |
| `codex/k07-dev-scripts` | `9541e6a7d092159931accf05ffa2692e8b41a2e9` | 删除 | ancestor of origin/main@99e169a |
| `codex/login-visual-refresh` | `89c885b37e30c80eb8432cafaca39ebd74b0ddf4` | 保留 | unique work; not proven redundant |
| `codex/opt-04-test-index` | `df181ce465bc81e2deca9c539b2ebb7ba7a9da0a` | 删除 | ancestor of origin/main@99e169a |
| `codex/opt-05-backend-layering` | `99c1f017f1f6c48f2f1d31dc0fe8f5c9d6a00586` | 删除 | ancestor of origin/main@99e169a |
| `codex/opt-base-ad63341` | `ad633416e436a23f28172db3bd5a11757fe573e0` | 删除 | ancestor of origin/main@99e169a |
| `codex/plan-c-acceptance-fixes` | `2265aee17a647d57b45cf56346f22b88b3763165` | 删除 | ancestor of origin/main@99e169a |
| `codex/r1-persist-deadline` | `61887f8a132391a3cf55de867ea802215fda5641` | 删除 | ancestor of origin/main@99e169a |
| `codex/startup-hotfix-20261006` | `85b6fb32e9f6ef785f94b356a39c761ebb49dd07` | 删除 | ancestor of origin/main@99e169a |
| `codex/ui-polish-model-discovery` | `11de2abbfee3f47db8d89c66b6785b19f0266017` | 删除 | ancestor of origin/main@99e169a |
| `feat/api-settings-page` | `0fa61e8a11acc4928eb3853ab5b30a46499e7d1a` | 保留 | unique work; not proven redundant |
| `frontend-backend-refactor` | `16a110940cd4de70a4ab08900633954d13e83f90` | 保留 | unique work; not proven redundant |
| `frontend-ui-revision` | `27bff16a67fa4e9b96416d3529069832b05e88ac` | 保留 | unique work; not proven redundant |
| `jmy1.0-2026-10-01` | `a690e418a462e386fb64d7dccf81112bc4798736` | 保留 | unique work; not proven redundant |
| `jmy1.0-2026-10-02` | `322ec231c3dbb288359d4f5b5065568b87a7f5c7` | 保留 | unique work; not proven redundant |
| `jmy1.0-2026-10-08` | `a459d673ee6e55a668c067a30545bf7f6fb98e6b` | 保留 | unique work; not proven redundant |
| `kongsc/a10-batch0-batch1` | `b62be76bf16d92331551395a939308898d629f14` | 删除 | ancestor of origin/main@99e169a |
| `kongsc/b08-contracts` | `15dacce75b29d0fd5105ab32c3ce45b63fb527f8` | 删除 | ancestor of origin/main@99e169a |
| `kongsc/b09-contracts` | `ffe6bf0c3cae38391d71581c94b8b6c30058975e` | 删除 | ancestor of origin/main@99e169a |
| `main` | `99e169af9cbb42b696a610bc785c1fb2fd94c93a` | 保留 | main branch |

## 整合与保留边界

- OPT-01～06 已在 #341；#339/#340 是旧底座上的重复 PR，关闭。
- #337 与 main 文件树一致，关闭；#342 的图谱查找和本地 `codex/extraction-perf@e8c20bd` 已随 #343 合入 main `1dbd272`。
- 旧 UI/API 配置、Windows 启动器、级联删除及早期契约分叉含独有实现，保持远端引用；这不表示这些功能已验收或应整体覆盖当前实现。
- 当前目录的未提交交接资料及其他 worktree 的本地环境不作为可丢弃文件处理。

## 最终结果与本地引用

- 原远端 195 个分支：删除 179，保留 16（main + 15 个含未确认独有内容的历史分叉）；本次创建的远端整合分支另已删除。
- 原本地 20 个分支：删除 19，仅保留 main；本次创建的本地整合分支另已删除。
- 原主检出已切回 main，原未提交三项资料的完整字节保存在 stash `5410571383d83078f79843c5575d9879d0419d21`，且内容已经在 main；不需要把旧任务看板整份覆盖回主线。
- 清理仅删除引用；其他干净 worktree 转为 detached HEAD，其目录与环境不删除。本次临时 worktree 已保存日志，但因其是当前聊天的主检出，宿主拒绝归档，保留为干净 detached HEAD；不影响分支引用清理。

| 本地分支 | 原 SHA | 处置 |
| --- | --- | --- |
| `claude/code-structure-review-handoff-49e73a` | `2675a44c2b6a9c0de0a68c29de07a5b5c7793341` | 删除；提交已覆盖或与 main 文件树相同 |
| `claude/home-topbar-nav` | `ad633416e436a23f28172db3bd5a11757fe573e0` | 删除；提交已覆盖或与 main 文件树相同 |
| `claude/knowledge-graph-ux-analysis-2e7400` | `983dcba0009abbbf56394771ebe361768dfae768` | 删除；提交已覆盖或与 main 文件树相同 |
| `claude/opt-05-remaining-tasks-78755a` | `3f26766d39d8c8cd1a6334b7e781d58ff40496cc` | 删除；提交已覆盖或与 main 文件树相同 |
| `claude/opt01-06-review-submit-598cc3` | `030408e80609107ee37f7585cfa374c42af1037a` | 删除；提交已覆盖或与 main 文件树相同 |
| `claude/project-sidebar-missing-conversations-79b4f7` | `3f26766d39d8c8cd1a6334b7e781d58ff40496cc` | 删除；提交已覆盖或与 main 文件树相同 |
| `claude/ui-pine-redesign` | `445bfc9ecd7e51267ddd1c42b956fe7ae5c4241b` | 删除；提交已覆盖或与 main 文件树相同 |
| `codex/extraction-perf` | `e8c20bde31fe34d8022cf010d26f1e35e010bd8c` | 删除；提交已覆盖或与 main 文件树相同 |
| `codex/invite-hover-refactor` | `e0b26e7ecb4aff2f9701443a9de2fd81e0968a5b` | 删除；提交已覆盖或与 main 文件树相同 |
| `codex/opt-01-doc-archive` | `f10d44fb671fc4b69c97eedce080f0f7ee87e4f5` | 删除；提交已覆盖或与 main 文件树相同 |
| `codex/opt-02-test-waits` | `eca579caf262522056a57b65b30601d9688c6dbf` | 删除；提交已覆盖或与 main 文件树相同 |
| `codex/opt-03-test-fixtures` | `36c1f928af174140cb8b0e25c279e1f36b2ed99f` | 删除；提交已覆盖或与 main 文件树相同 |
| `codex/opt-04-test-index` | `df181ce465bc81e2deca9c539b2ebb7ba7a9da0a` | 删除；提交已覆盖或与 main 文件树相同 |
| `codex/opt-05-backend-layering` | `99c1f017f1f6c48f2f1d31dc0fe8f5c9d6a00586` | 删除；提交已覆盖或与 main 文件树相同 |
| `codex/opt-06-base` | `ffef748b7c67f7a7d009c78373111e2bd24c8bbe` | 删除；提交已覆盖或与 main 文件树相同 |
| `codex/opt-06a-compatible` | `7cccaaa4ad2eda36b27fe1dd38dca66879669a1b` | 删除；提交已覆盖或与 main 文件树相同 |
| `codex/opt-06b-extraction` | `2f49e14339fdea2c79c713736bb454c2785f1f78` | 删除；提交已覆盖或与 main 文件树相同 |
| `codex/opt-06c-materials` | `936b41ef24e361fe720ebb5861a72d925e3cef3f` | 删除；提交已覆盖或与 main 文件树相同 |
| `codex/opt-06d-student-graph` | `3974731efa8727b0ac885bcce221ab2875c1f724` | 删除；提交已覆盖或与 main 文件树相同 |
| `main` | `99e169af9cbb42b696a610bc785c1fb2fd94c93a` | 保留并更新 |
