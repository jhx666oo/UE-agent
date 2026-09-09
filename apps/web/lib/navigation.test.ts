import { describe, expect, it } from "vitest";
import { isNavigationItemActive, primaryNavigation } from "./navigation";

describe("isNavigationItemActive", () => {
  it("matches a parent route but does not make the home item active everywhere", () => {
    expect(isNavigationItemActive("/u1/results", "/u1")).toBe(true);
    expect(isNavigationItemActive("/u1/results", "/")).toBe(false);
    expect(isNavigationItemActive("/", "/")).toBe(true);
  });

  it("keeps the primary navigation focused on business modules", () => {
    expect(primaryNavigation.map((item) => item.label)).toEqual(["总览", "城市项目", "政策资料", "参数设置"]);
    expect(primaryNavigation.some((item) => item.label.includes("工作台") || item.label.includes("U1"))).toBe(false);
  });
});
