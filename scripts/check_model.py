"""Check model readiness without exposing credentials; --call performs one request."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.service import analyze_item, demo_mode, init_db
from app.provider import ProviderError
from app.schemas import AnalysisInput
from app.database import SessionLocal


async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--call",action="store_true",help="实际调用一次当前模型；可能产生费用")
    args=parser.parse_args()
    missing=[name for name in ["LLM_BASE_URL","LLM_MODEL","LLM_API_KEY"] if not os.getenv(name)]
    print(json.dumps({"mode":"demo" if demo_mode() else "provider","missing_settings":missing,"call_performed":False},ensure_ascii=False))
    if not args.call: return
    if demo_mode() or missing: raise SystemExit("未调用：请在本地.env配置模型并设置DEMO_MODE=false。不要把密钥发到聊天。")
    init_db()
    try:
        with SessionLocal() as db:
            output=await analyze_item(db,AnalysisInput(title="合成连接测试",ad_copy="普通产品说明",feedback="我只划走卡片，页面却自己打开商店了",industry="工具",media_scene="天气",landing_type="应用下载",material_format="图文"))
        print(json.dumps({"call_performed":True,"model_info":output.model_info.model_dump(),"labels":[x.label for x in output.labels],"risk":output.overall_risk,"requires_human_review":output.requires_human_review,"assessment_status":output.assessment_status,"evidence":[x.model_dump() for x in output.evidence],"uncertainties":output.uncertainties},ensure_ascii=False))
    except ProviderError as exc:
        raise SystemExit(exc.code+": "+str(exc)+"；兼容API不一定支持严格JSON Schema，需确认该模型的能力。") from exc


if __name__=="__main__": asyncio.run(main())
