import Link from "next/link";
import React from "react";
import { IconArrowRight } from "@tabler/icons-react";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent } from "@ue-agent/ui/components/card";

export function EmptyState({
  title,
  description,
  actionLabel,
  actionHref,
}: Readonly<{
  title: string;
  description: string;
  actionLabel?: string;
  actionHref?: string;
}>) {
  return (
    <Card>
      <CardContent className="flex min-h-52 flex-col items-center justify-center px-6 text-center">
        <div className="mb-4 flex size-10 items-center justify-center rounded-full bg-surface-selected text-primary">—</div>
        <h2 className="text-base font-semibold">{title}</h2>
        <p className="mt-1 max-w-md text-sm leading-6 text-muted-foreground">{description}</p>
        {actionLabel && actionHref ? (
          <Button asChild variant="outline" size="sm" className="mt-5">
            <Link href={actionHref}>
              {actionLabel}
              <IconArrowRight size={15} stroke={1.8} />
            </Link>
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}
