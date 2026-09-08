import { describe, expect, it } from "vitest";
import { isNavigationItemActive } from "./navigation";

describe("isNavigationItemActive", () => {
  it("matches a parent route but does not make the home item active everywhere", () => {
    expect(isNavigationItemActive("/u1/results", "/u1")).toBe(true);
    expect(isNavigationItemActive("/u1/results", "/")).toBe(false);
    expect(isNavigationItemActive("/", "/")).toBe(true);
  });
});
