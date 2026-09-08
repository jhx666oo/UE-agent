"use client";

import React from "react";
import { Input } from "@ue-agent/ui/components/input";
import { Label } from "@ue-agent/ui/components/label";
import { Badge } from "@ue-agent/ui/components/badge";
import type { ParameterDefinition } from "@/lib/api";

export function U1ParameterField({
  definition,
  value,
  onChange,
  formulaValue,
}: Readonly<{
  definition: ParameterDefinition;
  value: number | string | null;
  formulaValue?: string;
  onChange: (value: number | string | null) => void;
}>) {
  const isFormula = definition.inputKind === "formula";
  const inputValue = isFormula ? formulaValue ?? "" : value ?? "";

  return (
    <div className="space-y-2">
      <div className="flex items-start justify-between gap-3">
        <Label htmlFor={`parameter-${definition.id}`}>
          {definition.id} {definition.name}
          {definition.required ? <span className="ml-1 text-danger">*</span> : null}
        </Label>
        {isFormula ? <Badge variant="info">公式值</Badge> : null}
      </div>
      <Input
        id={`parameter-${definition.id}`}
        type={definition.valueType === "number" ? "number" : "text"}
        inputMode={definition.valueType === "number" ? "decimal" : undefined}
        value={inputValue}
        readOnly={isFormula}
        onChange={(event) => {
          if (isFormula) return;
          const nextValue = event.target.value;
          if (nextValue === "") {
            onChange(null);
          } else if (definition.valueType === "number") {
            const numberValue = Number(nextValue);
            onChange(Number.isNaN(numberValue) ? null : numberValue);
          } else {
            onChange(nextValue);
          }
        }}
      />
      <p className="text-xs text-muted-foreground">
        {definition.unit} · {definition.sourceType} · {definition.excelCell}
        {definition.parityStatus === "needs_business_confirmation" ? " · 待业务确认" : ""}
      </p>
    </div>
  );
}
