import { describe,it,expect } from "vitest";
import { suggestRecommendationLabels,recommendationIsActive, type ReviewRecommendation } from "./review-recommendations";
const rec=(action:string):ReviewRecommendation=>({category:"product",action,rationale:"依据原文",priority:"P1",expected_metric:"待确认",guardrail_metric:"待确认"});
const labels=["forced_or_unexpected_jump","return_path_friction","weak_first_three_seconds"];
describe("人工复核建议关联",()=>{
 it("保留返回标签时移除跳转和视频建议",()=>{
  const actions=["核查跳转触发机制","优化视频前3秒内容","修复Deeplink返回逻辑"];
  const links=actions.map(x=>suggestRecommendationLabels(rec(x),labels));
  expect(links).toEqual([[labels[0]],[labels[2]],[labels[1]]]);
  expect(actions.filter((_,i)=>recommendationIsActive(links[i],[labels[1]]))).toEqual([actions[2]]);
 });
 it("多标签共用建议在一个关联仍保留时继续保留",()=>{
  const links=suggestRecommendationLabels(rec("核查跳转触发机制及返回路径"),labels);
  expect(links).toEqual([labels[0],labels[1]]);
  expect(recommendationIsActive(links,[labels[1]])).toBe(true);
 });
 it("无法识别的建议需人工关联，不猜测归属",()=>{
  expect(suggestRecommendationLabels(rec("verify_flow"),labels)).toEqual([]);
  expect(recommendationIsActive([],[labels[1]])).toBe(false);
 });
});
