from __future__ import annotations
import base64, csv, io, json, os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session
from .comprehensive import COMPREHENSIVE_OPTIONAL, COMPREHENSIVE_REQUIRED, aggregate_comprehensive, inspect_image, to_data_url
from .database import SessionLocal
from .agent import resume_agent_run, start_agent_run
from .evaluation import calculate_metrics
from .experiment import assign_experiment
from .models import Analysis, ExperimentAssignment, HumanReview, PromptVersion
from .pii import detect_sensitive_columns
from .provider import OpenAICompatibleProvider, ProviderError
from .schemas import AgentResumeInput, AnalysisInput, AnalysisOutput, ExperimentInput, PromptCreate, ReviewInput
from .service import ROOT, analyze_and_save, demo_mode, init_db, persist_analysis, save_review

@asynccontextmanager
async def lifespan(app): init_db(); yield
app=FastAPI(title="Ad Experience Insight Assistant API",version="1.0.0",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=[os.getenv("FRONTEND_ORIGIN","http://localhost:3000")],allow_credentials=False,allow_methods=["*"],allow_headers=["*"])
def get_db():
    db=SessionLocal()
    try: yield db
    finally: db.close()

@app.get("/api/health")
def health():
    provider=OpenAICompatibleProvider(); mode="demo" if demo_mode() else "provider"
    return {"status":"ok","mode":mode,"provider_adapter_configured":provider.configured,"provider":provider.provider if provider.configured else None,"model":provider.model if provider.configured else None,"rag":"local_tfidf","image_review_enabled":os.getenv("ENABLE_IMAGE_REVIEW","false").lower()=="true","synthetic_demo":mode=="demo"}

def provider_http_error(exc: ProviderError) -> HTTPException:
    status={"provider_not_configured":503,"image_review_disabled":503,"provider_timeout":504,"provider_rate_limit":429}.get(exc.code,502)
    return HTTPException(status,detail={"code":exc.code,"message":str(exc)})

@app.post("/api/analyses")
async def create_analysis(item: AnalysisInput,db:Session=Depends(get_db)):
    try: return await analyze_and_save(db,item)
    except ProviderError as exc: raise provider_http_error(exc)
    except ValueError as exc:
        code=str(exc).split(":",1)[0]
        raise HTTPException(400,detail={"code":code if code.endswith("error") or code=="policy_guardrail_triggered" else "validation_error","message":str(exc).split(":",1)[-1].strip()})
    except Exception as exc: raise HTTPException(500,detail={"code":"unknown_error","message":"分析失败，请检查输入后重试"}) from exc

@app.post("/api/agent/runs")
async def create_agent_run(item:AnalysisInput,db:Session=Depends(get_db)):
    try:
        thread_id,result=await start_agent_run(item)
        output=result.get("output")
        if output:
            persist_analysis(db,item,AnalysisOutput.model_validate(output))
        interrupted=result.get("__interrupt__")
        return {
            "thread_id":thread_id,
            "status":"awaiting_review" if interrupted else result.get("status","completed"),
            "output":output,
            "trace":result.get("trace",[]),
            "interrupt":interrupted[0].value if interrupted else None,
        }
    except ProviderError as exc: raise provider_http_error(exc)
    except ValueError as exc: raise HTTPException(400,detail={"code":"validation_error","message":str(exc)}) from exc

@app.post("/api/agent/runs/{thread_id}/resume")
async def resume_agent(thread_id:str,payload:AgentResumeInput,db:Session=Depends(get_db)):
    try:
        result=await resume_agent_run(thread_id,payload.model_dump())
    except Exception as exc:
        raise HTTPException(404,detail={"code":"agent_run_not_found","message":"任务不存在、已完成或服务已重启"}) from exc
    output=result.get("output")
    if output:
        row=db.get(Analysis,output["analysis_id"])
        if row:
            save_review(db,row,ReviewInput(reviewer="agent_human_reviewer",decision=payload.decision,notes=payload.notes))
    return {"thread_id":thread_id,"status":result.get("status","completed"),"output":output,"trace":result.get("trace",[]),"human_decision":result.get("human_decision")}

@app.get("/api/agent/graph")
def agent_graph():
    return {
        "name":"ad-review-agent",
        "nodes":["validate_input","retrieve_policy","analyze_risk","human_review","finalize"],
        "safety_boundary":"Agent 只分析和建议；高风险进入人工中断，不执行下线、处罚或投放修改。",
        "persistence":"进程内检查点，仅用于本地 Demo；生产环境需替换为持久化 checkpointer。",
    }

def _image_mime(content: bytes) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"): return "image/png"
    if content.startswith(b"\xff\xd8\xff"): return "image/jpeg"
    if len(content)>=12 and content[:4]==b"RIFF" and content[8:12]==b"WEBP": return "image/webp"
    return None

@app.post("/api/analyses/image")
async def create_image_analysis(payload:str=Form(...),file:UploadFile=File(...),db:Session=Depends(get_db)):
    try: item=AnalysisInput.model_validate_json(payload)
    except Exception as exc: raise HTTPException(400,detail={"code":"validation_error","message":"图片分析参数无效"}) from exc
    content=await file.read(5*1024*1024+1)
    if len(content)>5*1024*1024: raise HTTPException(400,detail={"code":"validation_error","message":"图片不能超过 5MB"})
    mime=_image_mime(content)
    if not mime: raise HTTPException(400,detail={"code":"validation_error","message":"仅支持真实的 PNG、JPEG 或 WebP 图片"})
    item=item.model_copy(update={"image_filename":file.filename or "uploaded-image"})
    image_data_url=f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"
    try: return await analyze_and_save(db,item,image_data_url)
    except ProviderError as exc: raise provider_http_error(exc)
    except ValueError as exc: raise HTTPException(400,detail={"code":"validation_error","message":str(exc)}) from exc

@app.get("/api/analyses")
def list_analyses(risk:str|None=None,review_required:bool|None=None,db:Session=Depends(get_db)):
    stmt=select(Analysis).order_by(desc(Analysis.created_at)).limit(200)
    if risk: stmt=stmt.where(Analysis.overall_risk==risk)
    if review_required is not None: stmt=stmt.where(Analysis.requires_human_review==review_required)
    rows=db.scalars(stmt).all()
    return [{"id":x.id,"created_at":x.created_at,"input":x.input_json,"output":x.original_output_json} for x in rows]

@app.delete("/api/analyses/{analysis_id}",status_code=204)
def delete_analysis(analysis_id:str,db:Session=Depends(get_db)):
    row=db.get(Analysis,analysis_id)
    if not row: raise HTTPException(404,"记录不存在")
    db.delete(row); db.commit(); return Response(status_code=204)

@app.post("/api/analyses/{analysis_id}/reviews")
def review(analysis_id:str,payload:ReviewInput,db:Session=Depends(get_db)):
    row=db.get(Analysis,analysis_id)
    if not row: raise HTTPException(404,"记录不存在")
    return save_review(db,row,payload)

REQUIRED=["title","ad_copy","feedback","industry","media_scene","landing_type","material_format"]
@app.get("/api/batch/template")
def batch_template():
    body=",".join(REQUIRED+["first_three_seconds"])+"\n演示游戏素材,限时福利,点击后自动跳转且返回很多次,游戏,锁屏,Deeplink,竖版视频,前三秒只有空镜\n"
    return Response(body,media_type="text/csv",headers={"Content-Disposition":"attachment; filename=synthetic_demo_template.csv"})

@app.post("/api/batch")
async def batch(file:UploadFile=File(...),db:Session=Depends(get_db)):
    if not file.filename.lower().endswith(".csv"): raise HTTPException(400,detail={"code":"validation_error","message":"仅支持 CSV 文件"})
    content=await file.read(2*1024*1024+1)
    if len(content)>2*1024*1024: raise HTTPException(400,detail={"code":"validation_error","message":"文件不能超过 2MB"})
    try: text=content.decode("utf-8-sig"); reader=csv.DictReader(io.StringIO(text)); fields=reader.fieldnames or []
    except UnicodeDecodeError: raise HTTPException(400,detail={"code":"validation_error","message":"请使用 UTF-8 编码"})
    sensitive=detect_sensitive_columns(fields)
    if sensitive: raise HTTPException(400,detail={"code":"policy_guardrail_triggered","message":"检测到不允许的敏感字段："+", ".join(sensitive)})
    missing=[x for x in REQUIRED if x not in fields]
    unknown=[x for x in fields if x not in REQUIRED+["first_three_seconds"]]
    if missing or unknown: raise HTTPException(400,detail={"code":"validation_error","message":f"缺少字段 {missing}；未知字段 {unknown}"})
    results=[]; errors=[]
    for n,row in enumerate(reader,start=2):
        try: results.append((await analyze_and_save(db,AnalysisInput(**row))).model_dump())
        except Exception as exc: errors.append({"row":n,"message":str(exc)[:200]})
    return {"processed":len(results),"failed":len(errors),"results":results,"errors":errors}

@app.get("/api/comprehensive/template")
def comprehensive_template():
    fields=COMPREHENSIVE_REQUIRED+COMPREHENSIVE_OPTIONAL
    rows=[
        ["AD-001","点击后自动跳转，连续返回很多次还是回不去","游戏福利素材","限时福利，点击查看详情","游戏","锁屏","Deeplink","图片","","ad-001.png"],
        ["AD-001","图片上的字很小，看不清楚","游戏福利素材","限时福利，点击查看详情","游戏","锁屏","Deeplink","图片","","ad-001.png"],
        ["AD-002","页面打开和返回都正常","工具介绍素材","功能说明与适用条件","工具","天气","Web","图文","","ad-002.png"],
    ]
    stream=io.StringIO(newline=""); writer=csv.writer(stream); writer.writerow(fields); writer.writerows(rows)
    return Response("\ufeff"+stream.getvalue(),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=comprehensive-demo-template.csv"})

@app.post("/api/comprehensive")
async def comprehensive(table:UploadFile=File(...),images:list[UploadFile]|None=File(default=None),db:Session=Depends(get_db)):
    if not table.filename or not table.filename.lower().endswith(".csv"):
        raise HTTPException(400,detail={"code":"validation_error","message":"反馈表仅支持 CSV 文件"})
    raw=await table.read(2*1024*1024+1)
    if len(raw)>2*1024*1024:
        raise HTTPException(400,detail={"code":"validation_error","message":"反馈表不能超过 2MB"})
    try:
        text=raw.decode("utf-8-sig"); reader=csv.DictReader(io.StringIO(text)); fields=reader.fieldnames or []
    except UnicodeDecodeError:
        raise HTTPException(400,detail={"code":"validation_error","message":"反馈表请使用 UTF-8 编码"})
    sensitive=detect_sensitive_columns(fields)
    if sensitive:
        raise HTTPException(400,detail={"code":"policy_guardrail_triggered","message":"检测到不允许的敏感字段："+", ".join(sensitive)})
    missing=[x for x in COMPREHENSIVE_REQUIRED if x not in fields]
    unknown=[x for x in fields if x not in COMPREHENSIVE_REQUIRED+COMPREHENSIVE_OPTIONAL]
    if missing or unknown:
        raise HTTPException(400,detail={"code":"validation_error","message":f"缺少字段 {missing}；未知字段 {unknown}"})
    parsed=list(reader)
    if not parsed or len(parsed)>200:
        raise HTTPException(400,detail={"code":"validation_error","message":"反馈表需包含 1-200 行数据"})

    image_catalog={}
    uploaded={}
    for file in images or []:
        if not file.filename: continue
        if file.filename in uploaded:
            raise HTTPException(400,detail={"code":"validation_error","message":f"图片文件名重复：{file.filename}"})
        content=await file.read(5*1024*1024+1)
        if len(content)>5*1024*1024:
            raise HTTPException(400,detail={"code":"validation_error","message":f"图片 {file.filename} 超过 5MB"})
        mime=_image_mime(content)
        if not mime:
            raise HTTPException(400,detail={"code":"validation_error","message":f"{file.filename} 不是有效的 PNG、JPEG 或 WebP"})
        uploaded[file.filename]=(content,mime)
        semantic_review=not demo_mode() and os.getenv("ENABLE_IMAGE_REVIEW","false").lower()=="true"
        image_catalog[file.filename]=inspect_image(file.filename,content,mime,semantic_review)

    analyzed=[]; errors=[]
    for n,row in enumerate(parsed,start=2):
        ad_id=(row.get("ad_id") or "").strip(); feedback=(row.get("feedback") or "").strip()
        if not ad_id or not feedback:
            errors.append({"row":n,"ad_id":ad_id,"message":"ad_id 和 feedback 不能为空"}); continue
        filename=(row.get("image_filename") or "").strip()
        item=AnalysisInput(
            title=(row.get("title") or f"广告 {ad_id}").strip(), ad_copy=(row.get("ad_copy") or "").strip(), feedback=feedback,
            industry=(row.get("industry") or "其他").strip(), media_scene=(row.get("media_scene") or "其他").strip(),
            landing_type=(row.get("landing_type") or "其他").strip(), material_format=(row.get("material_format") or ("图片" if filename else "其他")).strip(),
            first_three_seconds=(row.get("first_three_seconds") or "").strip() or None, image_filename=filename or None,
        )
        try:
            image_url=to_data_url(*uploaded[filename]) if filename in uploaded else None
            result=await analyze_and_save(db,item,image_url)
            analyzed.append({"ad_id":ad_id,"image_filename":filename,"result":result})
        except Exception as exc:
            errors.append({"row":n,"ad_id":ad_id,"message":str(exc)[:200]})
            analyzed.append({"ad_id":ad_id,"image_filename":filename,"result":None})
    report=aggregate_comprehensive(analyzed,image_catalog)
    report["processed"]=sum(1 for x in analyzed if x["result"] is not None)
    report["failed"]=len(errors)
    report["errors"]=errors
    return report

@app.get("/api/overview")
def overview(db:Session=Depends(get_db)):
    rows=db.scalars(select(Analysis)).all(); total=len(rows)
    risks={k:sum(x.overall_risk==k for x in rows) for k in ["low","medium","high","critical"]}
    reviewed=db.scalar(select(func.count()).select_from(HumanReview)) or 0
    return {"today_analyses":total,"risk_distribution":risks,"review_rate":round(reviewed/max(1,total),3),"average_latency_ms":round(sum(x.original_output_json.get("model_info",{}).get("latency_ms",0) for x in rows)/max(1,total)),"synthetic_demo":True}

@app.get("/api/prompts")
def prompts(db:Session=Depends(get_db)): return [{"version":x.version,"name":x.name,"content":x.content,"is_active":x.is_active,"created_at":x.created_at} for x in db.scalars(select(PromptVersion).order_by(desc(PromptVersion.id))).all()]
@app.post("/api/prompts")
def create_prompt(payload:PromptCreate,db:Session=Depends(get_db)):
    count=db.scalar(select(func.count()).select_from(PromptVersion)) or 0; version=f"custom-v{count+1}.0"
    row=PromptVersion(version=version,name=payload.name,content=payload.content,is_active=False); db.add(row); db.commit(); return {"version":version}
@app.post("/api/prompts/{version}/activate")
def activate_prompt(version:str,db:Session=Depends(get_db)):
    row=db.scalar(select(PromptVersion).where(PromptVersion.version==version))
    if not row: raise HTTPException(404,"版本不存在")
    for p in db.scalars(select(PromptVersion)).all(): p.is_active=p.id==row.id
    db.commit(); return {"active":version}

@app.post("/api/experiment/assign")
def experiment(payload:ExperimentInput,db:Session=Depends(get_db)):
    assigned=assign_experiment(payload.anonymous_user_id)
    existing=db.scalar(select(ExperimentAssignment).where(ExperimentAssignment.anonymous_id_hash==assigned["anonymous_id_hash"]))
    if not existing: db.add(ExperimentAssignment(anonymous_id_hash=assigned["anonymous_id_hash"],bucket=assigned["bucket"],group_name=assigned["group"])); db.commit()
    return {"bucket":assigned["bucket"],"group":assigned["group"]}

@app.post("/api/evaluation/run")
async def run_evaluation(db:Session=Depends(get_db)):
    if not demo_mode() and os.getenv("ALLOW_PROVIDER_EVALUATION","false").lower()!="true":
        raise HTTPException(400,detail={"code":"provider_evaluation_disabled","message":"真实模型批量评测默认关闭；确认成本后设置 ALLOW_PROVIDER_EVALUATION=true"})
    records=json.loads((ROOT/"data"/"synthetic_records.json").read_text(encoding="utf-8")); eval_rows=[x for x in records if x["split"]=="evaluation"]
    gold=[]; pred=[]; risks=[]; reviews=[]; latencies=[]
    for row in eval_rows:
        result=await analyze_and_save(db,AnalysisInput(**row["input"])); gold.append(set(row["gold_labels"])); pred.append({x.label for x in result.labels}); risks.append(row["gold_risk"]); reviews.append(result.requires_human_review); latencies.append(result.model_info.latency_ms)
    metrics=calculate_metrics(gold,pred,risks,reviews); metrics.update({"records":len(eval_rows),"average_latency_ms":round(sum(latencies)/len(latencies)),"estimated_cost_per_analysis_usd":0,"mode":"deterministic_demo","warning":"这些是本地合成评测结果，不代表真实线上模型或业务效果。"})
    report="# 评测报告\n\n> 本报告由本地合成评测集实际运行生成，不代表线上业务效果。\n\n```json\n"+json.dumps(metrics,ensure_ascii=False,indent=2)+"\n```\n"
    (ROOT/"docs"/"evaluation-report.md").write_text(report,encoding="utf-8")
    return metrics
