import * as React from "react";
import { cn } from "@ue-agent/ui/lib/cn";

const Separator = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => <div ref={ref} role="separator" className={cn("h-px w-full bg-border", className)} {...props} />,
);
Separator.displayName = "Separator";

export { Separator };
