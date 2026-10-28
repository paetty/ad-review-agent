export function assessmentTitle(status?: string): string {
  if (status === "insufficient_evidence") return "证据不足，暂不分类";
  if (status === "issue_detected") return "发现问题线索，待核查";
  if (status === "no_explicit_issue") return "未见明确问题，不等于审核通过";
  return "分析结果";
}

export function resultLabelName(label: string, status: string | undefined, names: Record<string, string>): string {
  if (label === "no_issue" && status === "insufficient_evidence") return "暂不分类（证据不足）";
  return names[label] || label;
}
