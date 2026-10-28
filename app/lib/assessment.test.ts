import { describe, expect, it } from "vitest";
import { assessmentTitle, resultLabelName } from "./assessment";

describe("evidence-state presentation", () => {
  it("never renders insufficient evidence as a normal/pass result", () => {
    expect(resultLabelName("no_issue", "insufficient_evidence", { no_issue: "未发现明确问题" })).toBe("暂不分类（证据不足）");
    expect(assessmentTitle("insufficient_evidence")).toContain("暂不分类");
  });
  it("keeps normal feedback separate from audit approval", () => {
    expect(assessmentTitle("no_explicit_issue")).toContain("不等于审核通过");
    expect(resultLabelName("no_issue", "no_explicit_issue", { no_issue: "未发现明确问题" })).toBe("未发现明确问题");
  });
  it("presents issue labels as clues instead of proven violations", () => {
    expect(assessmentTitle("issue_detected")).toContain("线索");
    expect(resultLabelName("unclear_material", "issue_detected", { unclear_material: "素材不清晰" })).toBe("素材不清晰");
  });
});
