export type ReviewRecommendation={category:string;action:string;rationale:string;priority:string;expected_metric:string;guardrail_metric:string};
export function suggestRecommendationLabels(r:ReviewRecommendation, available:string[]):string[]{
 const text=r.action+" "+r.rationale;
 const patterns:Record<string,RegExp>={
  forced_or_unexpected_jump:/非预期跳转|强制跳转|自动跳转|跳转触发|点击意图|点击行为/,
  return_path_friction:/返回路径|返回逻辑|返回机制|返回层级|返回成功|返回原媒体|一键返回|回不去|退出路径/,
  malicious_or_suspicious_redirect:/恶意|病毒|钓鱼|诈骗|域名|重定向链路/,
  misleading_claim:/误导宣传|绝对化|宣传依据|无法验证|夸大/,
  vulgar_or_inappropriate_content:/低俗|色情|内容安全|不适内容/,
  excessive_ad_frequency:/频控|频率|曝光次数|频繁/,
  repetitive_material:/素材轮换|素材重复|轮换池|冷却/,
  unclear_material:/清晰|分辨率|字号|可读性|对比度/,
  stale_material:/过期|有效期|活动日期|活动时间|失效信息|陈旧/,
  weak_first_three_seconds:/前三秒|前3秒|开场|开头|空镜/,
  irrelevant_targeting:/相关性|场景匹配|行业匹配|人群匹配/,
  potential_privacy_risk:/隐私|权限|通讯录|授权|数据最小化/,
  no_issue:/保持监测|无需自动限制|补充.*信息|补充具体操作/,
 };
 return available.filter(label=>patterns[label]?.test(text));
}
export function recommendationIsActive(links:string[],labels:string[]):boolean{
 return links.some(x=>labels.includes(x));
}
