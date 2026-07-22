# Mastery Ledger frontend redesign plan

Status: approved direction, implementation in progress
Started: 2026-07-21
Primary target: packaged Windows desktop application (`MasteryLedger.exe`)

This document is the restart-safe implementation contract for replacing the current editorial/dashboard frontend with a durable desktop workbench. Update the status checklist and implementation log whenever a slice is completed. Do not infer completion from a mockup, a passing unit test, or an old build artifact.

## 1. Product outcome

Mastery Ledger should feel like a focused local knowledge tool:

- an Obsidian-like workbench structure without copying Obsidian branding;
- a real shadcn/ui `new-york` neutral shell with Lucide icons;
- a narrow activity rail that remains available when the wider navigation pane is collapsed;
- a contextual left pane that is collapsible, resizable, accessible, and persistent;
- System, Light, and Dark appearance modes;
- Infield's proven CodeMirror reading palette and typography for long-form learning content;
- no source ingestion, course authoring, research, or exam generation inside the application.

The application must continue to respect `MASTERY_LEDGER_DESIGN_DECISIONS.md`. This redesign changes presentation and navigation, not the product boundary or durable learning artifacts.

## 2. Approved visual direction

### 2.1 Shell model

```text
┌────────────────────────────────────────────────────────────────────┐
│ Workspace / current location                   Search      Actions │
├──────┬──────────────────────┬──────────────────────────────────────┤
│      │ Workspace header     │                                      │
│  S   │ Context search       │                                      │
│  G   ├──────────────────────┤         Primary content canvas       │
│  E   │ Courses / chapters   │                                      │
│  R 3 │ Exams / review queue │         lesson / glossary / exam     │
│      │                      │                                      │
│  ⚙   │ Settings             │                                      │
└──────┴──────────↔───────────┴──────────────────────────────────────┘
  48px       220-360px
 activity    contextual navigation pane
 rail
```

- The activity rail stays visible at approximately 48px.
- The contextual pane defaults to 272px and clamps to 220-360px.
- Collapsing the pane leaves the activity rail visible.
- Narrow windows use an overlay/off-canvas contextual pane.
- A right inspector is optional future work, not a phase-one dependency.
- Panels are flat and edge-to-edge with one-pixel separators. Avoid floating dashboard cards as the default page structure.

### 2.2 Navigation information architecture

| Destination | Contextual pane | Main canvas |
| --- | --- | --- |
| Study | Course and chapter tree | Published lesson reader |
| Glossary | Course filter and term search | Glossary index and definitions |
| Exams | Exam filters and resumable attempts | Ready-exam register and details |
| Review | Due queue and count | Review overview or active session |
| Settings | Pinned at the rail bottom | Appearance, scheduling, workspace, and accessibility |

`Review curve` is a Settings / Scheduling page, not a top-level destination. `Due review` becomes the Review destination and may show a badge.

### 2.3 Anti-generic rules

Remove or avoid:

- oversized marketing-style serif headlines;
- decorative numbered folios where the number is not meaningful sequence data;
- warm-paper textures, novelty gradients, ornamental seals, and card grids as shell decoration;
- uppercase microcopy used only to make a block look designed;
- page-specific popup chrome when a shadcn primitive exists;
- broad element selectors that make later theme work unpredictable.

Use:

- compact, stable desktop chrome;
- semantic shadcn variables instead of raw page colors;
- restrained six-pixel control radius derived from a `0.625rem` root radius;
- visible keyboard focus and predictable hover/selected states;
- content density appropriate for daily use;
- the **mastery spine** as the single signature element: a thin progress line with meaningful checkpoints beside course/chapter navigation.

## 3. Theme and reading contracts

Shell appearance and document appearance are separate owners.

### 3.1 Shell theme

- Modes: `system`, `light`, `dark`.
- System mode follows `prefers-color-scheme` and updates when the OS preference changes.
- Use official shadcn neutral semantic variables for background, foreground, card, popover, primary, secondary, muted, accent, destructive, border, input, ring, and sidebar roles.
- The shell preference belongs to application-local settings, not a course workspace.
- Do not rely on `localStorage`: the desktop backend uses a changing loopback port and pywebview starts in private mode.

### 3.2 Infield reading preset

This is the default for Study lessons, long explanations, source disclosures, and other long-form learning surfaces:

```text
document font:
  -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen,
  Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif

code font:
  'Geist Mono', 'JetBrains Mono', 'Cascadia Code',
  'SFMono-Regular', ui-monospace, monospace

font size:              16px
line height:            1.7
reading measure:        720px
body weight:            450
letter spacing:         -0.011em
paragraph gap:          0.5em
list indent:            0.9em
list marker left:       0.1em
list marker gap:        0.3em
task marker width:      1.2em
proportional space:     0.27em
font smoothing:         antialiased / grayscale on macOS
```

Heading rhythm:

- H1: `1.35em`, weight 700, line-height 1.3, `0.15em` top and `0.1em` bottom space;
- H2: `1.2em`, weight 700, line-height 1.35, `0.15em` top and `0.1em` bottom space;
- H3: `1.1em`, weight 600, line-height 1.4, `0.12em` top and `0.06em` bottom space;
- H4-H6 remain close to body scale so long lessons do not become landing pages.

Infield Light core content colors:

- canvas `#ffffff`;
- foreground and H1 `#1f1f1f`;
- muted foreground `#737373`;
- surfaces `#ececed` and `#e3e3e4`;
- accent `#5e6ad2`;
- selection `#d6d9f3` with `#1f1f1f` text.

Infield Dark core content colors:

- canvas `#1e1e1e`;
- foreground `#c9cacb`;
- H1 `#dedfe0`, H2 `#d3d4d5`, H3 `#c5c6c7`;
- muted foreground `#a0a0a0`;
- surfaces `#202020` and `#282828`;
- accent `#0169cc`;
- links and caret `#6aaeff`;
- selection `#0d263e` with `#c9cacb` text.

The source contract was verified from the current Infield files:

- `C:\infield\src\lib\document-appearance-presets.ts`
- `C:\infield\src\lib\content-theme-registry.ts`
- `C:\infield\src\editor\herosTheme.ts`
- `C:\infield\src\styles\editor.css`

### 3.3 Sandboxed lesson boundary

`web/src/StudyReader.tsx` creates a complete sandboxed `srcDoc`. Outer shell variables do not cascade into that iframe. The selected content theme must therefore be passed into `lessonDocument(...)` and rendered into iframe-local variables/styles. Keep `sandbox=""`, the existing restrictive CSP, inert raw mode, and no script execution.

## 4. Technical architecture

### 4.1 Frontend foundation

Keep React + Vite. Add:

- Tailwind CSS v4 through the Vite plugin;
- shadcn/ui configuration with `new-york`, neutral, CSS variables, and Lucide;
- local utilities/components under `web/src/components/ui/`;
- Radix-backed primitives only where interaction requires them;
- `react-resizable-panels` through shadcn's Resizable wrapper;
- `lucide-react` for shell iconography.

Do not add React Router in the foundation slice. The current application has a small screen state machine and no approved deep-link/history requirement. Re-evaluate routing only if later workflows need durable internal URLs or browser-style back navigation.

### 4.2 CSS ownership

Target structure:

```text
web/src/styles/
  globals.css              Tailwind import, shadcn tokens, tiny resets
  shell.css                persistent activity rail, pane, toolbar, canvas
  content-theme.css        Infield content/document variables
  study.css                Study pane and lesson host only
  exams.css                exam list/player composition
  glossary.css             glossary composition
  settings.css             settings page composition
  onboarding.css           first-run and repair composition
```

`web/src/styles.css` remains temporarily as the legacy manifest during migration, then is removed after all mounted surfaces move to explicit owners. Do not rewrite every screen in one uncontrolled CSS change.

### 4.3 Frontend component owners

```text
web/src/components/layout/
  AppShell.tsx
  ActivityRail.tsx
  NavigationPane.tsx
  WorkspaceToolbar.tsx
  PaneResizeHandle.tsx

web/src/components/ui/
  copied shadcn primitives used by the app

web/src/context/
  AppearanceProvider.tsx

web/src/lib/
  appearance.ts
  navigation.ts
  utils.ts
```

Navigation items must come from a typed registry rather than hard-coded conditional button markup. A destination distinguishes page navigation from commands such as Rescan or Start review.

### 4.4 Persisted application UI settings

Add a dedicated API instead of changing the existing review-curve contract:

```text
GET /api/v1/settings/appearance
PUT /api/v1/settings/appearance
```

Schema `appearance-settings-v1`:

```json
{
  "schema_version": "appearance-settings-v1",
  "theme_mode": "system",
  "navigation_panel_open": true,
  "navigation_panel_width": 272,
  "content_theme": "infield"
}
```

Validation:

- `theme_mode`: `system | light | dark`;
- `navigation_panel_width`: integer clamped/validated to 220-360;
- `navigation_panel_open`: boolean;
- `content_theme`: initially only `infield`, leaving a versioned extension point.

Store these values in the existing SQLite `settings` table. They are application preferences and must not mutate course folders. The frontend applies a system-derived theme immediately, then reconciles with the persisted preference before mounting the main workbench.

### 4.5 Accessibility contract

- Rail and pane toggles have accessible names and `aria-expanded`/`aria-controls`.
- Resizer uses a focusable `separator`, horizontal value semantics, Left/Right Arrow resizing, Enter collapse/restore, and a visible focus ring.
- Icon-only buttons use shadcn Tooltip and accessible labels.
- Navigation selection and keyboard focus remain distinct.
- Nested course/chapter navigation follows tree keyboard behavior when it becomes a true hierarchy.
- `prefers-reduced-motion` and the existing `reduced_motion` setting suppress nonessential transitions.
- Light and dark content palettes must preserve readable contrast.

## 5. Migration phases and gates

### Phase 0 — Baseline and durable plan

- [x] Inspect actual Mastery Ledger owners and current desktop runtime.
- [x] Verify current shadcn/sidebar/resizable guidance.
- [x] Inspect the current Infield reading preset and theme registry.
- [x] Record this durable plan.
- [ ] Capture a current desktop screenshot/reference before deleting the old shell.

Gate: plan names real owners, non-goals, persistence boundary, and acceptance checks.

### Phase 1 — Foundation and persistence

- [x] Add Tailwind v4, shadcn config, aliases, utilities, and minimal primitives.
- [x] Add semantic shell and content token files.
- [x] Add backend appearance models/service/routes.
- [x] Add Python tests for defaults, validation, persistence, and workspace isolation.
- [x] Add frontend appearance resolver/provider tests.

Gate: old UI still works, production build passes, appearance settings survive backend restart, and no course file changes occur.

### Phase 2 — Persistent application shell

- [x] Add typed destination registry.
- [x] Add activity rail and workspace toolbar.
- [x] Add contextual pane and accessible resize handle.
- [x] Persist open/closed state and width.
- [x] Move workspace switcher into the pane header.
- [x] Move Rescan to the toolbar.
- [x] Move Settings to the rail footer.

Gate: Study, Glossary, Exams, and Review remain reachable; panel collapse/resize works with pointer and keyboard; 900px minimum desktop width is usable.

### Phase 3 — Study and Infield reading system

- [ ] Replace the nested Study catalog with the shell's contextual pane.
- [x] Apply exact Infield typography and light/dark palettes to lesson `srcDoc`.
- [x] Preserve CSP, sandbox, Read/Raw behavior, and parent isolation.
- [x] Add lesson theme, typography, and sandbox tests.
- [ ] Add the mastery spine to course/chapter progress only where real progress exists.

Gate: long lessons are readable at 16px/1.7/720px, theme changes reach the iframe, and sandbox behavior remains unchanged.

### Phase 4 — Glossary, Exams, and Review

- [ ] Migrate glossary filters/search to contextual navigation.
- [ ] Replace dashboard hero/card treatment with a compact exam workbench.
- [ ] Make Review a destination with due-count badge.
- [ ] Keep active exam delivery focused and distraction-free.
- [ ] Preserve answer locking, feedback, source disclosure, and resume behavior.

Gate: existing learning behavior tests pass and each destination has one clear primary job.

### Phase 5 — Settings, onboarding, and repair

- [ ] Add full Settings page: Appearance, Reading, Scheduling, Workspace, Accessibility.
- [ ] Move Review curve into Settings / Scheduling.
- [ ] Redesign onboarding and workspace repair with shadcn form/progress primitives.
- [ ] Preserve native folder selection and application/workspace boundary language.

Gate: a first-run user can configure a workspace, launch the workbench, change theme, and restart without losing preferences.

### Phase 6 — Cleanup and release verification

- [ ] Remove superseded legacy CSS and custom SVG icons.
- [ ] Verify no unused dependencies or duplicated primitive styles remain.
- [x] Run full Python and frontend tests.
- [x] Run TypeScript and Vite production build.
- [ ] Rebuild the Windows executable.
- [ ] Perform native desktop UAT for theme, resizing, collapse, keyboard focus, lesson reading, exams, and restart persistence.

Gate: packaged EXE serves the final matching frontend bundle and no generated/course artifacts are modified unexpectedly.

## 6. Verification matrix

Automated:

- backend appearance defaults and invalid-value rejection;
- persistence across a fresh API client/process;
- appearance values remain application-local;
- frontend theme resolution for System/Light/Dark;
- sidebar controlled-state and width clamping;
- lesson `srcDoc` contains the selected Infield palette and exact typography;
- sandbox and CSP remain restrictive;
- existing Study, Glossary, exam, review, packaging, and desktop tests;
- TypeScript no-emit and Vite build.

Manual desktop UAT:

- launch at 1440x900 and at the 900x640 minimum;
- collapse/expand with mouse and keyboard;
- resize pane to min/max and restart the app;
- change System/Light/Dark and restart;
- change OS theme while System mode is active;
- inspect a long lesson for measure, line height, headings, lists, tables, code, links, and selection;
- confirm popup/tooltips remain inside the desktop window and restore focus;
- launch and complete/resume an exam;
- verify reduced motion;
- verify no horizontal overflow at minimum window size.

## 7. Non-goals

- no course/source ingestion UI;
- no wiki authoring or lesson editing;
- no plugin system in this redesign;
- no arbitrary dock-and-drag pane system in phase one;
- no React Router migration without a separate requirement;
- no replacement of the FastAPI/SQLite backend;
- no weakening of the lesson sandbox;
- no installer, signing, or updater work inside frontend phases.

## 8. Restart instructions

When resuming:

1. Read this file and `MASTERY_LEDGER_DESIGN_DECISIONS.md`.
2. Inspect `git status --short`; preserve unrelated dirty work, especially `design-mockups/` and other untracked plans.
3. Find the first unchecked item in the active phase.
4. Reopen every named owner before editing; historical commits and this plan are pointers, not proof of current code.
5. Keep shell, content theme, page composition, and backend persistence in their assigned owners.
6. Update the checklist and implementation log only after verification.
7. Do not describe automated checks as native desktop UAT.

## 9. Implementation log

- 2026-07-21: EXE foundation completed and packaged desktop smoke passed.
- 2026-07-21: Online layout research selected the Obsidian-style rail + contextual pane workbench and shadcn `new-york` neutral shell.
- 2026-07-21: Current Infield content theme and 16px compact reading preset verified from live owners.
- 2026-07-21: Detailed redesign contract recorded; Phase 1 implementation started.
- 2026-07-21: Phase 1 foundation completed: Tailwind v4, shadcn `new-york` neutral tokens, aliases, content tokens, authenticated appearance persistence, and System/Light/Dark provider.
- 2026-07-21: Phase 2 shell foundation implemented with a 48px activity rail, collapsible 220-360px contextual pane, accessible resizer, toolbar Rescan, workspace picker, Review badge, and rail Settings action. Native desktop UAT remains open.
- 2026-07-21: Infield reading preset applied inside the sandboxed lesson document with explicit parent-theme propagation and light/dark tests. Moving the nested Study catalog into the contextual pane remains open.
- 2026-07-21: Automated gate passed: 99 Python tests, 11 frontend tests, TypeScript/Vite production build, and source desktop smoke (`backend=ready`, `frontend=ready`). The packaged EXE has not been rebuilt with this redesign and native visual/UAT remains open.
