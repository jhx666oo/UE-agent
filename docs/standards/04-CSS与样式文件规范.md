# CSS 与样式文件规范

## 1. 目标结构

```text
packages/ui/
├── components.json
└── src/
    ├── components/
    ├── icons/index.ts
    ├── lib/cn.ts
    └── styles/
        ├── tokens.css
        ├── base.css
        └── utilities.css

apps/web/
└── app/
    └── globals.css
```

`packages/ui` 是视觉和基础组件的唯一所有者。`apps/web` 只消费，不维护第二套样式系统。

## 2. components.json 固定策略

项目初始化后，下列关键项不得随意修改：

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "radix-nova",
  "rsc": true,
  "tsx": true,
  "tailwind": {
    "config": "",
    "css": "src/styles/tokens.css",
    "baseColor": "neutral",
    "cssVariables": true,
    "prefix": ""
  },
  "iconLibrary": "tabler"
}
```

实施时补充 monorepo alias。`style`、`baseColor`、`cssVariables` 和图标库属于设计系统决策，修改前必须写架构决策记录。

## 3. 文件职责

### 3.1 tokens.css

只包含：

- Tailwind v4 `@theme` 映射。
- `:root` 语义颜色。
- 字体、字号、间距、圆角、阴影、层级和图表 token。
- 必要的高对比度和 reduced-motion token。

不得包含页面选择器、业务组件选择器或具体路由样式。

### 3.2 base.css

只包含：

- 浏览器基础重置。
- `html`、`body`、标题、段落、链接和表单的基础行为。
- 字体平滑和数字特性。
- 全局焦点可见性。

不得包含 `.dashboard-card`、`.policy-page` 等业务类名。

### 3.3 utilities.css

只包含 Tailwind 无法稳定表达且重复出现的通用工具，例如隐藏滚动条、截断和数值对齐。新增工具必须至少有两个明确使用场景。

### 3.4 globals.css

只负责导入：

```css
@import "tailwindcss";
@import "@workspace/ui/styles/tokens.css";
@import "@workspace/ui/styles/base.css";
@import "@workspace/ui/styles/utilities.css";
```

业务样式不得持续堆积到 `globals.css`。

## 4. Token 命名

使用语义名称，不使用具体颜色名称：

```text
正确：--primary, --surface-selected, --text-muted, --status-warning
错误：--teal-700, --gray-card, --orange-text, --blue-button
```

使用者只关心作用，不依赖当前颜色值。禁止在组件中绕过语义 token 引用原始色板。

## 5. Tailwind 使用规则

### 5.1 允许

- 使用标准布局、间距、排版和响应式 utility。
- 使用 `bg-background`、`text-foreground`、`border-border` 等语义类。
- 使用 `cn()` 处理条件类名。
- 使用 CVA 定义组件有限变体。

### 5.2 限制

Arbitrary values 仅允许以下场景：

- 与应用骨架一致的固定尺寸，例如 `max-w-[1440px]`。
- Recharts、虚拟滚动和第三方控件需要的测量值。
- 浏览器兼容或精确布局无法由现有 token 表达。

每个 arbitrary value 必须能够说明来源。禁止随手使用 `mt-[13px]`、`text-[#0F766E]` 和 `shadow-[...]`。

### 5.3 禁止

- 组件内硬编码十六进制、RGB、HSL 或 OKLCH 品牌色。
- 使用 `!important` 解决层级或覆盖问题。
- 使用内联 `style` 写颜色、间距、字体和阴影。
- 在 JSX 中拼接不可静态分析的 Tailwind 类名。
- 使用 `transition-all`；必须指定变化属性。
- 在页面里复制一整套组件 CSS。
- 使用通配选择器影响业务组件后代。

## 6. CVA 变体规则

基础组件变体必须有限且有语义：

```text
Button.variant = primary | secondary | outline | ghost | destructive
Button.size = compact | default
Badge.tone = neutral | info | success | warning | danger
```

禁止 `green`、`blue`、`pretty`、`modern` 等外观型变体。页面不得新增一次性 Button variant。

## 7. CSS Modules 使用边界

只有以下情况允许 `*.module.css`：

- 复杂网格或 sticky 布局无法清晰地用 utility 表达。
- 第三方库需要结构化选择器覆盖。
- 打印布局或浏览器特定行为。

CSS Module 只能作用于当前组件，必须使用 token，不能复制基础组件样式。

## 8. 第三方 CSS

- 引入前检查体积、全局选择器和主题覆盖方式。
- 禁止引入侵入性高、会重置全站样式的未知 CSS 包。
- 第三方样式覆盖集中放在对应 adapter，不散落在页面。
- 不通过 CDN 注入运行时 CSS。

## 9. 层级规范

固定 z-index token：

| Token | 值 | 用途 |
|---|---:|---|
| `--z-base` | 0 | 普通内容 |
| `--z-sticky` | 20 | 固定表头和页面工具栏 |
| `--z-dropdown` | 40 | 菜单和 Popover |
| `--z-overlay` | 60 | 遮罩 |
| `--z-modal` | 80 | Dialog 和 Sheet |
| `--z-toast` | 100 | Toast |

页面不得使用 `z-[9999]`。层级冲突必须修复 stacking context，而不是继续提高数值。

## 10. 动效规范

- 默认持续时间 120-180ms。
- 只动画 `opacity` 和 `transform`，业务状态变化可动画颜色。
- 不使用页面进入动画、滚动劫持和无限循环装饰动画。
- Loading 使用 Skeleton，不使用持续旋转的大型图标。
- 所有非必要动效在 `prefers-reduced-motion` 下关闭。

## 11. 自动检查建议

实施阶段配置 Stylelint、ESLint 或自定义检查，至少拦截：

- `apps/web` 中出现硬编码颜色。
- 非 token 文件出现 `!important`。
- 页面文件直接写内联视觉样式。
- 引入白名单外组件库或图标库。
- 新增未登记的全局 CSS 文件。
