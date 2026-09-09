import { describe, expect, it } from "vitest";
import { isNavigationItemActive, primaryNavigation } from "./navigation";

describe("isNavigationItemActive", () => {
  it("matches a parent route but does not make the home item active everywhere", () => {
    expect(isNavigationItemActive("/u1/results", "/u1")).toBe(true);
    expect(isNavigationItemActive("/u1/results", "/")).toBe(false);
    expect(isNavigationItemActive("/", "/")).toBe(true);
  });

  it("ignores query strings when matching city compare", () => {
    expect(isNavigationItemActive("/", "/?scope=compare")).toBe(true);
    expect(isNavigationItemActive("/projects", "/?scope=compare")).toBe(false);
  });

  it("keeps the primary navigation to the four PRD modules", () => {
    expect(primaryNavigation.map((item) => item.label)).toEqual([
      "总览",
      "城市测算",
      "政策资料",
      "城市对比",
    ]);
    const banned = ["工作台", "U1", "城市项目", "参数设置"];
    expect(
      primaryNavigation.some((item) => banned.some((word) => item.label.includes(word))),
    ).toBe(false);
  });
});
