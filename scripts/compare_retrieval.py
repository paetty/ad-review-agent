"""A small declared development probe, not an independent retrieval benchmark."""
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.retrieval import PolicyRetriever

PROBES=[
    ("广告一键关闭 虚假关闭标志 关闭后继续弹出", "generic", "08-official-internet-advertising-summary-01"),
    ("虚假系统提示 误导点击 欺骗浏览广告", "generic", "08-official-internet-advertising-summary-02"),
    ("vivo 创意图片 落地跳转页面 审核范围", "vivo", "09-vivo-public-review-summary-00"),
    ("OPPO 素材 文案 落地页 内容一致性", "oppo", "10-oppo-public-review-summary-00"),
    ("匿名曝光 频控 24小时 同素材", "generic", "11-internal-demo-operations-00"),
    ("素材轮换 候选 重复反馈 有效触达", "generic", "11-internal-demo-operations-01"),
    ("治理交接 人工复核 导出 问题单", "generic", "11-internal-demo-operations-02"),
    ("返回原媒体 连续返回很多次", "generic", "01-navigation-return-01"),
]


def main():
    retriever=PolicyRetriever(ROOT/"data/policies")
    result={}
    for method in ["tfidf","bm25"]:
        hits=[]; reciprocal=[]; misses=[]
        for query,platform,expected in PROBES:
            chunks=retriever.search(query,top_k=4,platform=platform,method=method)
            ids=[x["chunk_id"] for x in chunks]
            hits.append(expected in ids)
            reciprocal.append(1/(ids.index(expected)+1) if expected in ids else 0)
            if expected not in ids: misses.append(query)
        result[method]={"queries":len(PROBES),"recall_at_4":sum(hits)/len(hits),"mrr_at_4":round(sum(reciprocal)/len(reciprocal),3),"misses":misses}
    output={"results":result,"boundary":"8条查询由开发者根据当前规则编写，只验证检索链路；不是独立盲测，不据此宣称算法优劣。Embedding与reranker未配置。"}
    (ROOT/".tmp").mkdir(exist_ok=True)
    (ROOT/".tmp/retrieval-development.json").write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(output,ensure_ascii=False,indent=2))


if __name__=="__main__": main()
