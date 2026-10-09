# API settings compact layout and searchable model picker

Date:2026-10-08. Baseline:e7291d2. Branch:codex/ui-polish-model-discovery. Status:DONE.

User requested parallel generation/vector API panels that fit one desktop page, then a single editable model picker instead of separate directory/manual fields.

Changed ModelSettingsView.vue, EmbeddingSettings.vue and scoped ui.css layout; added reusable ModelPicker.vue. Teacher panels use equal grid columns above1050px; shorter desktop viewports reduce spacing. Mobile stacks naturally without clipping. Provider/address share a row; repeated helper content moves to expandable help. Configuration state, operations, credentials, discovery cancellation and API behavior remain intact. Students have one compact generation panel and no vector component.

ModelPicker uses one input, substring filtering, an all-models toggle, freely typed names and an absolutely positioned scrollable popup. Arrow keys and Enter select; Esc, outside clicks and focus departure close. Large lists do not expand page height. Empty/failed discovery still permits manual names. Upward positioning preserves usable popup space near the viewport bottom.

Verification:
- RED:two new behavioral tests failed on missing filtering and keyboard selection before implementation.
- GREEN:four related frontend suites32 passed; type-check and build passed (existing chunk-size advisory).
- verify.sh basic passed:contract generation parity, structural and negative regression checks.
- Live teacher desktop1366x768,1440x900,1920x1080:parallel cards and collapsed help fit viewport. Also checked loaded directories, input filtering/all-models selection and custom dimension. At1366x768 cards end at691px, collapsed help at723px.
- Teacher/student1440px and390px fixture checks:visibility, configuration operations and no horizontal overflow passed. Mobile requires vertical scrolling to retain readable controls. Expanding optional help, multiple errors or clear confirmation can naturally increase height.

No backend, contract, migration or persistent settings changes. Local screenshots/browser scripts and provider mocks remain in ignored .local-run. No real provider discovery was used for picker checks. Local commit only, no push. Revert this task commit to recover old layout and picker interaction; no DB rollback required. User can refresh http://127.0.0.1:5322/settings/model to inspect.
