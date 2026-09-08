# UE Agent Repository Instructions

Read `docs/standards/00-规范总则.md` before making changes. Read the relevant detailed standards for the files in scope.

## Product rules

- U1 is the first complete business workflow.
- Core financial results must come from a deterministic, versioned calculation engine.
- Keep reference values, confirmed inputs, calculated values, and displayed values separate.
- Never turn missing data into zero or silently overwrite a confirmed value with crawler output.
- A formal result must bind the model version, source versions, and an immutable input snapshot.

## Frontend rules

- Use only shadcn/ui with Radix primitives, Tailwind CSS v4, and semantic CSS variables.
- Use only `@tabler/icons-react` for icons.
- Use TanStack Form with Zod, TanStack Query, TanStack Table, nuqs, Recharts, date-fns, and Sonner for their documented categories.
- Reuse `packages/ui` components before creating a new component.
- Do not hardcode brand colors, radii, shadows, or z-index in pages or components.
- Do not introduce Ant Design, MUI, Chakra, another icon family, or another table/form/chart library.
- Every async page or component must handle loading, empty, error, permission, and stale states where applicable.
- Follow `docs/standards/02-前端视觉设计系统.md`, `03-页面布局与交互规范.md`, and `04-CSS与样式文件规范.md`.

## Change discipline

- Inspect existing patterns and dependencies before adding code.
- Record the reuse decision before creating a new shared component or dependency.
- Do not change formulas, units, model semantics, the component system, or the theme without an approved architecture decision.
- Run applicable formatting, lint, type, test, accessibility, build, and end-to-end checks before claiming completion.
- Do not create branches, commits, pull requests, or production deployments unless the user explicitly authorizes them.

