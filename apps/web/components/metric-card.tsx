import React from "react";
import { Card, CardContent } from "@ue-agent/ui/components/card";

export function MetricCard({
  label,
  value,
  note,
  tone = "neutral",
}: Readonly<{
  label: string;
  value?: string;
  note?: string;
  tone?: "neutral" | "danger" | "success" | "warning";
}>) {
  const valueTone =
    tone === "danger"
      ? "text-danger"
      : tone === "success"
        ? "text-success"
        : tone === "warning"
          ? "text-warning"
          : "";
  return (
    <Card>
      <CardContent className="space-y-2 p-5">
        <p className="text-sm text-muted-foreground">{label}</p>
        <p className={`text-2xl font-semibold tracking-tight ${valueTone}`.trim()}>{value || "—"}</p>
        {note ? <p className="text-xs text-muted-foreground">{note}</p> : null}
      </CardContent>
    </Card>
  );
}
