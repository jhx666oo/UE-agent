import { Card, CardContent } from "@ue-agent/ui/components/card";

export function MetricCard({
  label,
  value,
  note,
}: Readonly<{
  label: string;
  value?: string;
  note?: string;
}>) {
  return (
    <Card>
      <CardContent className="space-y-2 p-5">
        <p className="text-sm text-muted-foreground">{label}</p>
        <p className="text-2xl font-semibold tracking-tight">{value || "—"}</p>
        {note ? <p className="text-xs text-muted-foreground">{note}</p> : null}
      </CardContent>
    </Card>
  );
}
