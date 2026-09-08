import { Badge, type BadgeProps } from "@ue-agent/ui/components/badge";

const STATUS_VARIANTS = {
  未开始: "neutral",
  待补数据: "warning",
  计算中: "info",
  已完成: "success",
  需复核: "danger",
} as const satisfies Record<string, NonNullable<BadgeProps["variant"]>>;

export type CalculationStatus = keyof typeof STATUS_VARIANTS;

export function StatusBadge({ status }: Readonly<{ status: CalculationStatus }>) {
  return <Badge variant={STATUS_VARIANTS[status]}>{status}</Badge>;
}
