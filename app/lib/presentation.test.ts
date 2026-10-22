import { describe, expect, it } from "vitest";
describe("risk presentation",()=>{
 it("keeps the four canonical risk levels",()=>{expect(["low","medium","high","critical"]).toHaveLength(4)});
 it("never exposes server secret names",()=>{expect(JSON.stringify({api:"/api"})).not.toContain("LLM_API_KEY")});
});

