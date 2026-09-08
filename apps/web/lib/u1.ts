export type U1Step = "scope" | "assumptions" | "data" | "calculate" | "review";

const U1_STEP_LABELS: Record<U1Step, string> = {
  scope: "测算范围",
  assumptions: "关键假设",
  data: "数据准备",
  calculate: "执行测算",
  review: "结果复核",
};

export function getU1StepLabel(step: U1Step) {
  return U1_STEP_LABELS[step];
}

export const U1_STEPS: readonly U1Step[] = ["scope", "assumptions", "data", "calculate", "review"];
