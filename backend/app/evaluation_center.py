"""Dataset selection, explicit provider opt-in and isolated evaluation records."""
from __future__ import annotations
import hashlib
import json
import time
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from .database import Base, SessionLocal
from .models import EvaluationRun, EvaluationItem, PromptVersion
from .evaluation import calculate_metrics
from .schemas import AnalysisInput
from .provider import OpenAICompatibleProvider, ProviderError
from .service import ROOT, analyze_item

router=APIRouter(prefix="/api/evaluations",tags=["统一评测中心"])
DEFINITIONS={
 "development":("新版开发集","用来发现错误和调整系统；单人复核的合成案例。",ROOT/"data/evaluation/feedback-candidates-v2.json","development"),
 "validation":("新版验证集","当前8条主要检查正常及否定表达；反复用于调优后不再独立。",ROOT/"data/evaluation/feedback-candidates-v2.json","validation"),
 "supplement":("补充开发集","12条已确认的高风险、多标签及模糊表达案例。",ROOT/"data/evaluation/supplement-12-reviewed-2026-10-27.json",None),
 "legacy":("旧版回归集","80条早期模板型合成案例，只用于回归，不代表自然语言泛化效果。",ROOT/"data/synthetic_records.json","evaluation"),
}

def load_dataset(key:str)->tuple[list[dict],dict]:
 if key not in DEFINITIONS: raise ValueError("未知数据集；留出候选不在此入口开放")
 title,description,path,split=DEFINITIONS[key]
 raw=path.read_bytes(); data=json.loads(raw)
 source=data if isinstance(data,list) else data["cases"]
 selected=[r for r in source if split is None or r.get("split")==split]
 rows=[]
 for n,r in enumerate(selected,1):
  if key=="supplement":
   if data.get("annotation_status")!="reviewed_single_owner":raise ValueError("补充案例尚未确认")
   inp=dict(title="合成开发案例",ad_copy="产品介绍与适用条件",feedback=r["feedback"],industry="工具",media_scene="天气",landing_type="Web",material_format="图文")
   state=r["status"];risk=r["risk"];review=r["review"]
  else:
   if key!="legacy" and (r.get("annotation_status")!="reviewed" or not r.get("reviewer")):raise ValueError("案例尚未复核")
   inp=r["input"];risk=r["gold_risk"];state=r.get("gold_assessment_status")
   review=r.get("gold_requires_human_review",risk in {"high","critical"} or state=="insufficient_evidence")
  item=AnalysisInput.model_validate(inp)
  rows.append({"record_id":str(r.get("record_id",r.get("id",f"{key}-{n}"))),"input":item.model_dump(),"labels":r["gold_labels"],"risk":risk,"status":state,"review":review})
 if not rows or len({x["record_id"] for x in rows})!=len(rows):raise ValueError("数据集为空或案例编号重复")
 return rows,{"id":key,"name":title,"description":description,"count":len(rows),"sha256":hashlib.sha256(raw).hexdigest(),"source":"synthetic_single_owner_or_template","status_reference_count":sum(r["status"] is not None for r in rows)}

class Selection(BaseModel):
 dataset:Literal["development","validation","supplement","legacy"]="development"
 mode:Literal["rules","provider"]="rules"

class RunRequest(Selection):
 dataset_sha256:str=Field(min_length=64,max_length=64)
 confirm_provider:bool=False

def preview(selection:Selection)->dict:
 rows,meta=load_dataset(selection.dataset)
 provider=OpenAICompatibleProvider()
 return {"dataset":meta,"mode":selection.mode,"analyses":len(rows),"expected_model_calls":len(rows) if selection.mode=="provider" else 0,
         "maximum_http_attempts":len(rows)*3 if selection.mode=="provider" else 0,
         "estimated_cost_usd":None if selection.mode=="provider" else 0,
         "model":provider.model if selection.mode=="provider" else "demo-engine-v1","provider_configured":provider.configured,
         "notice":"真实模型费用尚未定价；预计每条一次逻辑调用，超时/限流最多3次HTTP尝试。测试结果只写评测表，不进入业务分析量。"}

@router.get("/datasets")
def catalog():
 return {"datasets":[load_dataset(key)[1] for key in DEFINITIONS],"warning":"合成数据，非独立盲测；12条留出候选未开放运行。"}

@router.post("/preview")
def preview_endpoint(selection:Selection):
 return preview(selection)

def reserve_run(request:RunRequest)->tuple[int,list[dict],dict,dict]:
 rows,meta=load_dataset(request.dataset)
 if meta["sha256"]!=request.dataset_sha256:raise HTTPException(409,"数据集已变化，请重新预览")
 provider=OpenAICompatibleProvider()
 if request.mode=="provider":
  if not request.confirm_provider:raise HTTPException(400,"请确认本次真实模型调用数量及可能费用")
  if not provider.configured:raise HTTPException(503,"真实模型配置不完整")
 with SessionLocal() as db:
  active=db.scalar(select(PromptVersion).where(PromptVersion.is_active==True))
  prompt={"version":active.version if active else "evaluation-default","content":active.content if active else "基于输入和检索证据进行广告体验分析。"}
  # Prevent double-clicks/concurrent charge-bearing runs on this local prototype.
  old=db.scalars(select(EvaluationRun)).all()
  if any(x.metrics_json.get("status") in {"queued","running"} for x in old):raise HTTPException(409,"已有评测进行中，请等待完成")
  snapshot={"status":"queued","dataset":meta,"mode":request.mode,"total":len(rows),"processed":0,"failed":0,"prompt":prompt,"cost_usd":None if request.mode=="provider" else 0,"metrics":None}
  row=EvaluationRun(model_version=provider.model if request.mode=="provider" else "demo-engine-v1",prompt_version=prompt["version"],metrics_json=snapshot)
  db.add(row);db.commit();run_id=row.id
 return run_id,rows,snapshot,prompt

def summarize(items:list[dict],snapshot:dict)->dict:
 gold=[set(x["reference"]["labels"]) for x in items]
 pred=[{l["label"] for l in x["output"]["labels"]} if x["output"] else set() for x in items]
 risks=[x["reference"]["risk"] for x in items]
 reviews=[x["output"]["requires_human_review"] if x["output"] else False for x in items]
 predicted_risks=[x["output"]["overall_risk"] if x["output"] else "low" for x in items]
 metrics=calculate_metrics(gold,pred,risks,reviews,predicted_risks)
 known=[x for x in items if x["reference"]["status"] is not None]
 outputs=[x["output"] for x in items if x["output"]]
 metrics.update({"records":len(items),"failed":sum(x["output"] is None for x in items),
  "all_checks_match_count":sum(x["matched"] for x in items),"status_reference_count":len(known),
  "status_match_ratio":sum(x["checks"]["status"] is True for x in known)/len(known) if known else None,
  "average_measured_pipeline_ms":round(sum(x["measured_ms"] for x in items)/len(items),2),
  "input_tokens":sum(x["model_info"]["input_tokens"] for x in outputs),"output_tokens":sum(x["model_info"]["output_tokens"] for x in outputs),
  "tokens_simulated":snapshot["mode"]=="rules","estimated_cost_usd":snapshot["cost_usd"],
  "warning":"失败项按未命中计入指标；无状态参考的旧案例不比较状态。模型置信度不是准确率，费用未知不记为免费；失败调用用量可能未完整返回。"})
 return metrics

async def execute_run(run_id:int,rows:list[dict],snapshot:dict,prompt:dict):
 state={**snapshot,"status":"running"};items=[]
 def persist_state():
  with SessionLocal() as db:
   run=db.get(EvaluationRun,run_id);run.metrics_json=dict(state);db.commit()
 memory=create_engine("sqlite:///:memory:")
 try:
  persist_state()
  # Freeze prompt for this run; analyze_item never writes business analyses.
  Base.metadata.create_all(memory)
  with Session(memory) as evaluation_db:
   evaluation_db.add(PromptVersion(version=prompt["version"],name="评测快照",content=prompt["content"],is_active=True));evaluation_db.commit()
   for row in rows:
    started=time.perf_counter();output=None;error=None
    try:
     result=await analyze_item(evaluation_db,AnalysisInput.model_validate(row["input"]),mode_override=state["mode"])
     output=result.model_dump()
    except Exception as exc:
     error={"code":exc.code if isinstance(exc,ProviderError) else "analysis_error","message":"该条分析失败，可查看其他案例；失败项已计入分母。"}
    checks={"labels":output is not None and set(row["labels"])=={x["label"] for x in output["labels"]},
            "risk":output is not None and row["risk"]==output["overall_risk"],
            "status":None if row["status"] is None else output is not None and row["status"]==output["assessment_status"],
            "review":output is not None and row["review"]==output["requires_human_review"]}
    item={"record_id":row["record_id"],"input":row["input"],"reference":{k:row[k] for k in ["labels","risk","status","review"]},"output":output,"error":error,"checks":checks,"matched":all(x is not False for x in checks.values()),"measured_ms":round((time.perf_counter()-started)*1000,2)}
    items.append(item)
    with SessionLocal() as db:
     db.add(EvaluationItem(run_id=run_id,record_id=row["record_id"],gold_json=item["reference"],prediction_json=item));db.commit()
    state.update(processed=len(items),failed=sum(x["error"] is not None for x in items));persist_state()
  state.update(status="partial" if state["failed"] else "completed",metrics=summarize(items,state));persist_state()
 except Exception:
  state.update(status="failed",error="评测执行中断，已完成条目保留；重启服务后可重新运行。");persist_state()
 finally:memory.dispose()

@router.post("/runs",status_code=202)
async def start_run(request:RunRequest,background:BackgroundTasks):
 run_id,rows,snapshot,prompt=reserve_run(request)
 background.add_task(execute_run,run_id,rows,snapshot,prompt)
 return {"run_id":run_id,"status":"queued"}

@router.get("/runs")
def list_runs():
 with SessionLocal() as db:
  runs=db.scalars(select(EvaluationRun).order_by(EvaluationRun.id.desc()).limit(20)).all()
  return [{"run_id":x.id,"created_at":x.created_at,"model":x.model_version,"prompt_version":x.prompt_version,**{k:v for k,v in x.metrics_json.items() if k!="prompt"}} for x in runs]

@router.get("/runs/{run_id}")
def get_run(run_id:int):
 with SessionLocal() as db:
  row=db.get(EvaluationRun,run_id)
  if not row:raise HTTPException(404,"评测记录不存在")
  items=db.scalars(select(EvaluationItem).where(EvaluationItem.run_id==run_id).order_by(EvaluationItem.id)).all()
  return {"run_id":row.id,"model":row.model_version,"prompt_version":row.prompt_version,**{k:v for k,v in row.metrics_json.items() if k!="prompt"},"items":[x.prediction_json for x in items]}

def mark_interrupted_runs():
 with SessionLocal() as db:
  for run in db.scalars(select(EvaluationRun)).all():
   if run.metrics_json.get("status") in {"queued","running"}:run.metrics_json={**run.metrics_json,"status":"interrupted","error":"服务重启，未自动重试或继续付费调用，已完成条目保留。"}
  db.commit()
