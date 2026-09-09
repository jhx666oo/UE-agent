import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@ue-agent/ui/lib/cn";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-[14px] font-normal leading-5 tracking-normal transition-[background-color,border-color,color,box-shadow,transform] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring/40 active:translate-y-px disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-white shadow-sm hover:bg-primary-hover",
        secondary: "bg-surface-subtle text-foreground hover:bg-muted",
        outline: "border border-border-strong bg-surface text-foreground hover:bg-surface-subtle",
        ghost: "text-muted-foreground hover:bg-surface-subtle hover:text-foreground",
        danger: "bg-danger text-white shadow-sm hover:bg-danger/90",
      },
      size: {
        sm: "h-9 px-3.5",
        default: "h-10 px-4",
        lg: "h-11 px-5 text-[15px]",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
