import { render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { Topbar } from "./topbar";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

describe("Topbar", () => {
  it("keeps the new-project action horizontal and wide enough for Chinese text", () => {
    render(<Topbar />);

    const action = screen.getByRole("link", { name: "新增城市" });
    expect(action).toHaveClass("min-w-[104px]");
    expect(action).toHaveClass("whitespace-nowrap");
  });
});
