# UE-Agent Frontend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first runnable UE-Agent frontend foundation: a stable monorepo, the approved design system, a shared application shell, a project entry page, and a U1 city-selection measurement entry page.

**Architecture:** Use a pnpm monorepo with `apps/web` for the Next.js App Router application and `packages/ui` for the shared design tokens and primitive components. The first phase is frontend-only: route pages use typed local view models and explicit empty states, never fake business metrics; the calculation engine, crawler, authentication, and production deployment remain outside this phase.

**Tech Stack:** Next.js 16, React 19, TypeScript, Tailwind CSS v4, shadcn/ui-compatible Radix primitives, CVA, Tabler Icons, Vitest, Testing Library, pnpm.

## Global Constraints

- Follow `AGENTS.md`, `.github/instructions/frontend.instructions.md`, and `docs/standards/00-规范总则.md` through `docs/standards/06-前端验收检查表.md` before changing UI code.
- Use the fixed visual system: light-only warm-gray canvas, deep teal primary, 4px spacing grid, 6/8/12px radius scale, 40px normal controls, and no gradients, glassmorphism, neon colors, or decorative dashboard noise.
- Use only the approved UI stack; do not add a second component library, icon library, CSS framework, or charting library.
- All colors, radii, typography, shadows, z-index values, and motion tokens must come from shared CSS variables or the existing utility classes; no arbitrary color literals inside page components.
- The first phase must not invent business values, formulas, policy conclusions, crawler results, customer data, or default approvals. Missing data is represented by an empty, loading, or action-required state.
- New behavior is developed with TDD: write a failing test, verify the expected failure, implement the smallest passing change, then refactor only while tests remain green.
- A task is complete only after the relevant targeted test and the repository-level typecheck/build checks pass.

## File Map

- `package.json`, `pnpm-workspace.yaml`, `tsconfig.base.json`: workspace scripts and shared TypeScript settings.
- `apps/web/`: the Next.js application, route layouts, navigation, page composition, and app-level CSS entry point.
- `packages/ui/src/styles/`: the only shared CSS token, base, and utility layers.
- `packages/ui/src/components/`: reusable primitives with no domain-specific assumptions.
- `packages/ui/src/lib/`: small tested helpers such as class-name composition.
- `docs/superpowers/plans/`: implementation plans and their progress checkboxes.

---

### Task 1: Scaffold the pnpm workspace and package boundaries

**Files:**
- Create: `package.json`
- Create: `pnpm-workspace.yaml`
- Create: `tsconfig.base.json`
- Create: `apps/web/package.json`
- Create: `apps/web/next.config.ts`
- Create: `apps/web/tsconfig.json`
- Create: `apps/web/postcss.config.mjs`
- Create: `packages/ui/package.json`
- Create: `packages/ui/tsconfig.json`
- Create: `packages/ui/components.json`

**Interfaces:**
- Produces a workspace package named `@ue-agent/web` and a shared package named `@ue-agent/ui`.
- Produces root scripts `dev`, `build`, `lint`, `typecheck`, and `test` that delegate to the workspace packages.

- [ ] **Step 1: Create the workspace manifests and scripts**

Use these package boundaries and scripts:

```json
// package.json
{
  "name": "ue-agent",
  "private": true,
  "packageManager": "pnpm@10.13.1",
  "scripts": {
    "dev": "pnpm --filter @ue-agent/web dev",
    "build": "pnpm --filter @ue-agent/web build",
    "lint": "pnpm --filter @ue-agent/web lint",
    "typecheck": "pnpm --recursive typecheck",
    "test": "pnpm --recursive test"
  },
  "devDependencies": {
    "typescript": "^5.9.3"
  }
}
```

```yaml
// pnpm-workspace.yaml
packages:
  - apps/*
  - packages/*
```

```json
// apps/web/package.json
{
  "name": "@ue-agent/web",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "eslint .",
    "typecheck": "tsc --noEmit",
    "test": "vitest run"
  },
  "dependencies": {
    "@ue-agent/ui": "workspace:*",
    "@tabler/icons-react": "^3.34.0",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "next": "^16.1.6",
    "react": "^19.2.3",
    "react-dom": "^19.2.3",
    "tailwind-merge": "^3.5.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.8.0",
    "@testing-library/react": "^16.3.0",
    "@types/node": "^22.15.0",
    "@types/react": "^19.1.0",
    "@types/react-dom": "^19.1.0",
    "eslint": "^9.30.0",
    "eslint-config-next": "^16.1.6",
    "jsdom": "^26.1.0",
    "vitest": "^3.2.4"
  }
}
```

```json
// packages/ui/package.json
{
  "name": "@ue-agent/ui",
  "private": true,
  "exports": {
    "./styles/tokens.css": "./src/styles/tokens.css",
    "./styles/base.css": "./src/styles/base.css",
    "./styles/utilities.css": "./src/styles/utilities.css",
    "./components/*": "./src/components/*.tsx",
    "./lib/*": "./src/lib/*.ts"
  },
  "scripts": {
    "typecheck": "tsc --noEmit",
    "test": "vitest run"
  },
  "dependencies": {
    "@radix-ui/react-slot": "^1.2.4",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "tailwind-merge": "^3.5.0"
  },
  "devDependencies": {
    "@types/react": "^19.1.0",
    "@types/react-dom": "^19.1.0",
    "typescript": "^5.9.3",
    "vitest": "^3.2.4"
  }
}
```

- [ ] **Step 2: Add the TypeScript and Tailwind v4 configuration**

Configure `apps/web/tsconfig.json` to extend `../../tsconfig.base.json`, set `baseUrl` to `.`, map `@/*` to `./*`, and include `next-env.d.ts`, `.next/types/**/*.ts`, and `**/*.ts(x)`. Configure `packages/ui/tsconfig.json` to emit no files, use `jsx: react-jsx`, and include `src/**/*.ts(x)`.

Use `apps/web/postcss.config.mjs` with only the Tailwind v4 plugin:

```js
const config = { plugins: { "@tailwindcss/postcss": {} } };
export default config;
```

Use `packages/ui/components.json` with `style: "radix-nova"`, `rsc: true`, `tsx: true`, `tailwind.css: "apps/web/app/globals.css"`, `tailwind.baseColor: "neutral"`, `tailwind.cssVariables: true`, and `iconLibrary: "tabler"`.

- [ ] **Step 3: Install the workspace lockfile**

Run `pnpm install` from the repository root. Expected: a new `pnpm-lock.yaml` is created and both workspace packages resolve without peer-dependency errors that stop installation.

- [ ] **Step 4: Verify the empty scaffold**

Run `pnpm typecheck`. Expected: the command may report missing application entry files at this point; record that expected red result and continue to Task 2, where those files are added. Do not mark this task complete until the final task-level checks pass.

### Task 2: Establish shared tokens, base styles, and primitive UI components

**Files:**
- Create: `packages/ui/src/lib/cn.ts`
- Create: `packages/ui/src/lib/cn.test.ts`
- Create: `packages/ui/src/styles/tokens.css`
- Create: `packages/ui/src/styles/base.css`
- Create: `packages/ui/src/styles/utilities.css`
- Create: `packages/ui/src/components/button.tsx`
- Create: `packages/ui/src/components/badge.tsx`
- Create: `packages/ui/src/components/card.tsx`
- Create: `packages/ui/src/components/input.tsx`
- Create: `packages/ui/src/components/label.tsx`
- Create: `packages/ui/src/components/separator.tsx`
- Create: `packages/ui/src/components/skeleton.tsx`

**Interfaces:**
- `cn(...inputs: ClassValue[]): string` merges conditional class names and Tailwind conflicts.
- `Button`, `Badge`, `Card`, `CardHeader`, `CardContent`, `CardTitle`, `Input`, `Label`, `Separator`, and `Skeleton` are domain-agnostic shared primitives.

- [ ] **Step 1: Write the failing class-name test**

Create `packages/ui/src/lib/cn.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { cn } from "./cn";

describe("cn", () => {
  it("keeps conditional classes and resolves Tailwind conflicts", () => {
    expect(cn("px-2", false && "hidden", "px-4")).toBe("px-4");
  });
});
```

- [ ] **Step 2: Run the test to verify the expected failure**

Run `pnpm --filter @ue-agent/ui test src/lib/cn.test.ts`. Expected: FAIL because `./cn` does not exist.

- [ ] **Step 3: Implement the smallest `cn` helper and verify green**

Create `packages/ui/src/lib/cn.ts`:

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

Run the same targeted test. Expected: PASS.

- [ ] **Step 4: Add the shared CSS token layers**

Define the exact palette and scales from `docs/standards/02-前端视觉设计系统.md` in `tokens.css`, including `--background: #F7F7F5`, `--primary: #0F766E`, `--border: #E5E7EB`, the semantic status colors, chart colors, font stack, radius scale, spacing scale, and shadow scale. Add Tailwind v4 `@theme inline` mappings to the CSS variables.

Make `base.css` set `box-sizing`, body background/foreground/font, selection color, focus-visible outline, and form control font inheritance. Make `utilities.css` contain only named layout utilities used by the app shell: `page-container`, `section-label`, `text-balance`, and `focus-ring`.

- [ ] **Step 5: Add the primitive components**

Implement the primitives with `cn` and CVA. `Button` must support `default`, `secondary`, `outline`, `ghost`, and `danger` variants plus `sm`, `default`, and `lg` sizes. `Badge` must support `neutral`, `info`, `success`, `warning`, and `danger`. Cards must expose header/content/title/description slots. Inputs and labels must preserve accessible `htmlFor` and focus behavior. `Separator` and `Skeleton` must be presentational and token-based.

- [ ] **Step 6: Run the package checks**

Run `pnpm --filter @ue-agent/ui test`, `pnpm --filter @ue-agent/ui typecheck`, and `git diff --check`. Expected: all tests pass, TypeScript exits 0, and Git reports no whitespace errors.

### Task 3: Build the application shell and route navigation

**Files:**
- Create: `apps/web/app/globals.css`
- Create: `apps/web/app/layout.tsx`
- Create: `apps/web/app/page.tsx`
- Create: `apps/web/app/(workspace)/layout.tsx`
- Create: `apps/web/components/app-shell.tsx`
- Create: `apps/web/components/sidebar.tsx`
- Create: `apps/web/components/topbar.tsx`
- Create: `apps/web/components/page-header.tsx`
- Create: `apps/web/lib/navigation.ts`
- Create: `apps/web/lib/navigation.test.ts`

**Interfaces:**
- `isNavigationItemActive(pathname: string, href: string): boolean` returns true for an exact route or a child route, except `/` only matches `/`.
- `AppShell` composes sidebar, topbar, and a main content slot.

- [ ] **Step 1: Write and run the failing navigation tests**

Create `apps/web/lib/navigation.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { isNavigationItemActive } from "./navigation";

describe("isNavigationItemActive", () => {
  it("matches a parent route but does not make the home item active everywhere", () => {
    expect(isNavigationItemActive("/u1/results", "/u1")).toBe(true);
    expect(isNavigationItemActive("/u1/results", "/")).toBe(false);
    expect(isNavigationItemActive("/", "/")).toBe(true);
  });
});
```

Run `pnpm --filter @ue-agent/web test lib/navigation.test.ts` after workspace install. Expected: FAIL because `navigation.ts` does not exist.

- [ ] **Step 2: Implement navigation matching and verify green**

Implement `isNavigationItemActive` with normalized trailing slashes; return `pathname === href` for `/`, and otherwise return `pathname === href || pathname.startsWith(`${href}/`)`. Run `pnpm --filter @ue-agent/web test lib/navigation.test.ts` and expect PASS.

- [ ] **Step 3: Add the application CSS entry point and root layout**

Import Tailwind and the three `@ue-agent/ui` style layers in `apps/web/app/globals.css`. Set metadata to `UE-Agent｜长护险 UE 测算工作台`, and render `AppShell` from the workspace layout so every workspace route receives the same shell.

- [ ] **Step 4: Implement the shell components**

Use a 240px sidebar, a 56px topbar, a max content width of 1440px, a 64px collapsed-sidebar affordance, and the approved Tabler icon set. Navigation labels must be `工作台`, `项目`, `U1 城市选址`, `政策资料`, and `系统设置`. The shell must be responsive: sidebar becomes a top-level compact control under 768px; desktop layout must remain two-column at 1200px and above. The topbar must expose the current module name and a non-destructive “新建项目” action link to `/projects/new` without pretending that project creation exists yet.

- [ ] **Step 5: Add the root route and run route-level checks**

Render `/` as a concise welcome/overview entry that directs users to `/projects` and `/u1` without fake KPI numbers. Run `pnpm --filter @ue-agent/web test`, `pnpm --filter @ue-agent/web typecheck`, and `pnpm --filter @ue-agent/web build`. Expected: all pass.

### Task 4: Add project and U1 measurement entry pages

**Files:**
- Create: `apps/web/app/(workspace)/projects/page.tsx`
- Create: `apps/web/app/(workspace)/projects/new/page.tsx`
- Create: `apps/web/app/(workspace)/u1/page.tsx`
- Create: `apps/web/components/empty-state.tsx`
- Create: `apps/web/components/metric-card.tsx`
- Create: `apps/web/components/status-badge.tsx`
- Create: `apps/web/lib/u1.ts`
- Create: `apps/web/lib/u1.test.ts`

**Interfaces:**
- `U1Step` is the union `"scope" | "assumptions" | "data" | "calculate" | "review"`.
- `getU1StepLabel(step: U1Step): string` returns a fixed Chinese label without business calculations.
- `EmptyState` and `MetricCard` are reusable domain-light compositions built only from shared primitives.

- [ ] **Step 1: Write and run the failing U1 step-label test**

Create `apps/web/lib/u1.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { getU1StepLabel } from "./u1";

describe("getU1StepLabel", () => {
  it("uses stable Chinese labels for the U1 workflow", () => {
    expect(getU1StepLabel("scope")).toBe("测算范围");
    expect(getU1StepLabel("assumptions")).toBe("关键假设");
    expect(getU1StepLabel("data")).toBe("数据准备");
    expect(getU1StepLabel("calculate")).toBe("执行测算");
    expect(getU1StepLabel("review")).toBe("结果复核");
  });
});
```

Run the targeted test. Expected: FAIL because `u1.ts` does not exist.

- [ ] **Step 2: Implement the label map and verify green**

Create the `U1Step` union and an exhaustive `Record<U1Step, string>` map. Implement `getU1StepLabel` as a direct lookup. Run the targeted test and expect PASS.

- [ ] **Step 3: Build the reusable empty and status compositions**

`EmptyState` must accept a title, description, optional action label, and optional action href. `MetricCard` must accept a label, a value, and an optional note; it must render an em dash when the value is absent. `StatusBadge` must map only known statuses (`未开始`, `待补数据`, `计算中`, `已完成`, `需复核`) to the approved semantic badge variants.

- [ ] **Step 4: Implement the project list and new-project entry**

`/projects` must show the page header, a short explanation of the project entity, one primary link to `/projects/new`, and an empty state that says no project data has been connected yet. `/projects/new` must show the first-step form shell (project name, target city, base month) with labels and a disabled “保存并继续” button until backend persistence exists; the page must explicitly state that this phase only establishes the interface.

- [ ] **Step 5: Implement the U1 entry page**

`/u1` must show the U1 workflow stepper, a measurement-scope card, an assumptions/data readiness section with em dashes instead of invented values, and a clear action to start a project. It must explain that the first release will verify scope, assumptions, data, calculation, and review in that order. Do not render a “全国最优城市” result or any return/profit number before the calculation service is implemented.

- [ ] **Step 6: Run frontend checks**

Run `pnpm --filter @ue-agent/web test`, `pnpm --filter @ue-agent/web typecheck`, `pnpm --filter @ue-agent/web lint`, and `pnpm --filter @ue-agent/web build`. Expected: all pass with no placeholder or hardcoded-color lint findings.

### Task 5: Update repository documentation and complete verification

**Files:**
- Modify: `README.md`
- Modify: `docs/UE-Agent-详细开发规范-v0.1.md`
- Modify: `docs/standards/06-前端验收检查表.md`
- Create: `pnpm-lock.yaml`

- [ ] **Step 1: Update the README implementation status**

Replace the statement that business code has not started with the actual first-phase scope: frontend foundation, app shell, shared UI primitives, project entry, and U1 entry page are available; calculation engine and data connectors are next phases.

- [ ] **Step 2: Record the development checkpoint**

Add a dated checkpoint to the detailed development specification with the exact commands that passed: `pnpm test`, `pnpm typecheck`, `pnpm lint`, and `pnpm build`.

- [ ] **Step 3: Run the repository verification suite**

Run:

```bash
git diff --check
pnpm test
pnpm typecheck
pnpm lint
pnpm build
```

Expected: every command exits 0. Also inspect `git status --short` and confirm only the planned workspace, documentation, configuration, and lockfile changes are present.

- [ ] **Step 4: Commit the development checkpoint and push**

Use two focused commits on the authorized `main` branch:

```bash
git add README.md AGENTS.md .cursor .github docs
git commit -m "docs: add UE Agent engineering standards"
git push origin main

git add package.json pnpm-workspace.yaml tsconfig.base.json pnpm-lock.yaml apps packages README.md docs
git commit -m "feat: add UE Agent frontend foundation"
git push origin main
```

Expected: both pushes update `https://github.com/jhx666oo/UE-agent` and `git status --short --branch` reports a clean `main` tracking `origin/main`.

## Self-review

- Scope is intentionally limited to a runnable interface foundation; no business formula or external data is fabricated.
- Every behavior helper in the first phase has a test-first task with a specified red and green command.
- CSS and component constraints map directly to `docs/standards/00-规范总则.md` through `06-前端验收检查表.md`.
- The plan uses one icon library, one UI primitive family, one CSS token layer, one app shell, and one root workspace package boundary.
