# UE Agent Copilot Instructions

Follow `/AGENTS.md` and the canonical standards in `/docs/standards/`.

- Treat this as a high-density, trust-first long-term care insurance decision workspace, not a marketing site.
- Reuse `packages/ui`; do not recreate base controls in page files.
- Use shadcn/ui + Radix, Tailwind v4 semantic tokens, and Tabler Icons only.
- Do not introduce a competing component, icon, table, form, chart, date, or notification library.
- Do not hardcode brand colors, radii, shadows, or z-index.
- Implement loading, empty, error, permission, validation, and stale-result states where applicable.
- Keep public reference values separate from business-confirmed inputs.
- Never guess missing policy or financial inputs, and never let an LLM calculate authoritative UE results.
- Before finishing, apply `/docs/standards/06-前端验收检查表.md` and report the checks actually run.

