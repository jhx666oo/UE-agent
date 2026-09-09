import { describe, expect, it } from "vitest";
import { buttonVariants } from "./button";

describe("button visual contract", () => {
  it("uses a stable Chinese typography baseline and keeps labels on one line", () => {
    const classes = buttonVariants();

    expect(classes).toContain("whitespace-nowrap");
    expect(classes).toContain("text-[14px]");
    expect(classes).toContain("font-normal");
    expect(classes).toContain("leading-5");
  });
});
