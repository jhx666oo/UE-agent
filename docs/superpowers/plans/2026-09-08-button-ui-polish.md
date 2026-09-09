# UE-Agent Button UI Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify Chinese button typography and spacing, and make the topbar “新建项目” action a stable single-line horizontal button.

**Architecture:** Keep the existing shared `@ue-agent/ui` Button component as the only source of button typography and state styles. Apply the topbar-specific minimum width and icon size in `apps/web/components/topbar.tsx`, without changing routes, API behavior, or business calculations.

**Tech Stack:** React 19, Next.js, Tailwind CSS v4, class-variance-authority, Tabler Icons, Vitest, Testing Library.

## Global Constraints

- Keep the existing Chinese font fallback chain and do not add a font dependency.
- Use 14px regular-weight text with a stable 20px line height for the shared button baseline.
- Keep all button labels on one line with `whitespace-nowrap`.
- Keep the existing teal primary color and light theme.
- Do not change business data, routes, model formulas, or the Dashboard information architecture.
- Do not commit changes until the user explicitly authorizes a commit.

---

### Task 1: Add regression tests for the button visual contract

**Files:**
- Create: `packages/ui/src/components/button.test.ts`
- Create: `apps/web/components/topbar.test.tsx`

**Interfaces:**
- Consumes: `buttonVariants` from `@ue-agent/ui/components/button` and the existing `Topbar` component.
- Produces: Tests that fail until the shared button and topbar classes implement the approved typography and sizing contract.

- [ ] **Step 1: Write the failing shared-button test**

```ts
import { describe, expect, it } from "vitest";
import { buttonVariants } from "./button";

describe("button visual contract", () => {
  it("uses a stable Chinese typography baseline and keeps labels on one line", () => {
    const classes = buttonVariants();

    expect(classes).toContain("whitespace-nowrap");
    expect(classes).toContain("text-[14px]");
    expect(classes).toContain("font-normal");
    expect(classes).toContain("leading-5");
  });
});
```

- [ ] **Step 2: Write the failing topbar test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Topbar } from "./topbar";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

describe("Topbar", () => {
  it("keeps the new-project action horizontal and wide enough for Chinese text", () => {
    render(<Topbar />);

    const action = screen.getByRole("link", { name: "新建项目" });
    expect(action).toHaveClass("min-w-[104px]");
    expect(action).toHaveClass("whitespace-nowrap");
  });
});
```

- [ ] **Step 3: Run the focused tests and verify they fail**

Run:

```bash
pnpm --filter @ue-agent/ui test -- button.test.ts
pnpm --filter @ue-agent/web test -- topbar.test.tsx
```

Expected: FAIL because the current shared button has `text-sm font-medium` and the current topbar action does not have `min-w-[104px]`.

### Task 2: Implement the shared button and topbar visual system

**Files:**
- Modify: `packages/ui/src/components/button.tsx`
- Modify: `apps/web/components/topbar.tsx`
- Modify: `apps/web/app/globals.css`

**Interfaces:**
- Consumes: Existing `Button` variants, size variants, `navigationItems`, and `IconPlus`.
- Produces: A shared button class contract and a topbar action that remains one line at desktop widths.

- [ ] **Step 1: Update the shared button typography and interaction classes**

Replace the base class string in `packages/ui/src/components/button.tsx` with:

```ts
"inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-[14px] font-normal leading-5 tracking-normal transition-[background-color,border-color,color,box-shadow,transform] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring/40 active:translate-y-px disabled:pointer-events-none disabled:opacity-50"
```

Update the size variants to:

```ts
size: {
  sm: "h-9 px-3.5",
  default: "h-10 px-4",
  lg: "h-11 px-5 text-[15px]",
},
```

Keep the existing color variants unchanged, including the explicit `text-white` primary and danger labels.

- [ ] **Step 2: Make the topbar action explicit**

In `apps/web/components/topbar.tsx`, change the icon and action class to:

```tsx
<Button asChild size="sm" className="min-w-[104px] shrink-0">
  <Link href="/projects/new">
    <IconPlus size={15} stroke={1.8} />
    <span className="whitespace-nowrap">新建项目</span>
  </Link>
</Button>
```

This removes the desktop-only text hiding so the action always communicates its purpose, while preserving the existing route.

- [ ] **Step 3: Include the shared UI package in Tailwind scanning**

Add this directive immediately after the Tailwind import in `apps/web/app/globals.css`:

```css
@source "../../../packages/ui/src";
```

This makes the utility classes authored in `@ue-agent/ui` part of the Web app's generated CSS. Without it, the class strings exist in the DOM but utilities such as `inline-flex`, `gap-1.5`, `h-9`, and `leading-5` are missing from the browser stylesheet.

### Task 3: Run verification and inspect the result

**Files:**
- No new files.

**Interfaces:**
- Consumes: Updated shared button classes and topbar test coverage.
- Produces: Verified UI behavior and a clean working tree except for the intended button changes and design documents.

- [ ] **Step 1: Run focused UI tests**

Run:

```bash
pnpm --filter @ue-agent/ui test -- button.test.ts
pnpm --filter @ue-agent/web test -- topbar.test.tsx
```

Expected: PASS.

- [ ] **Step 2: Run project checks**

Run:

```bash
pnpm typecheck
pnpm lint
pnpm build
```

Expected: all commands exit with code 0.

- [ ] **Step 3: Check the browser result**

Open `http://localhost:3000/` and verify the top-right action renders as one horizontal row with a 15px plus icon, 14px Chinese text, 36px height, and no text wrapping.

- [ ] **Step 4: Review the diff**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only the approved button component, topbar, tests, and design/plan documents are changed. Do not commit until the user explicitly authorizes it.
