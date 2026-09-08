import { describe, expect, it } from "vitest";
import { getU1StepLabel } from "./u1";

describe("getU1StepLabel", () => {
  it("uses stable Chinese labels for the U1 workflow", () => {
    expect(getU1StepLabel("scope")).toBe("测算范围");
    expect(getU1StepLabel("assumptions")).toBe("关键假设");
    expect(getU1StepLabel("data")).toBe("数据准备");
    expect(getU1StepLabel("calculate")).toBe("执行测算");
    expect(getU1StepLabel("review")).toBe("结果复核");
  });
});
