---
applyTo: "apps/web/**/*.{ts,tsx,css},packages/ui/**/*.{ts,tsx,css}"
---

# Frontend path instructions

Read `docs/standards/02-前端视觉设计系统.md`, `docs/standards/03-页面布局与交互规范.md`, and `docs/standards/04-CSS与样式文件规范.md`.

- Search `packages/ui` before creating a component.
- Base components belong in `packages/ui/src/components/base`; business pages consume them.
- Use semantic classes such as `bg-background`, `text-foreground`, and `border-border`.
- Do not use hardcoded color utilities, inline visual styles, `!important`, arbitrary shadows, or arbitrary z-index.
- Use Tabler Icons only, with the shared icon export and standard stroke width.
- Forms require visible labels, units, inline validation, and explicit blank-versus-zero behavior.
- Data views require loading, empty, error, permission, and stale states where applicable.
- Verify responsive layouts at 1440, 1280, 1024, 768, and 390 pixels.

