from __future__ import annotations
import time
from sklearn.metrics import precision_recall_fscore_support, f1_score
from .taxonomy import LABELS

def calculate_metrics(gold: list[set[str]], predicted: list[set[str]], risks: list[str] | None=None, predicted_reviews: list[bool] | None=None, predicted_risks: list[str] | None=None) -> dict:
    if not gold or len(gold) != len(predicted): raise ValueError("评测需要非空且对齐的预测与标准答案")
    for values in (risks, predicted_reviews, predicted_risks):
        if values is not None and len(values) != len(gold): raise ValueError("风险及复核列表长度必须与样本数一致")
    y_true=[[int(label in row) for label in LABELS] for row in gold]
    y_pred=[[int(label in row) for label in LABELS] for row in predicted]
    p,r,f,s=precision_recall_fscore_support(y_true,y_pred,average=None,zero_division=0)
    per={label:{"precision":round(float(p[i]),3),"recall":round(float(r[i]),3),"f1":round(float(f[i]),3),"support":int(s[i])} for i,label in enumerate(LABELS)}
    exact=sum(a==b for a,b in zip(gold,predicted))/max(1,len(gold))
    result={"per_label":per,"macro_f1":round(float(f1_score(y_true,y_pred,average="macro",zero_division=0)),3),"micro_f1":round(float(f1_score(y_true,y_pred,average="micro",zero_division=0)),3),"exact_match_ratio":round(exact,3)}
    if risks:
        high=[i for i,x in enumerate(risks) if x in {"high","critical"}]
        result["high_risk_support"] = len(high)
        result["high_risk_recall"] = round(sum(predicted_risks[i] in {"high", "critical"} for i in high)/len(high),3) if high and predicted_risks is not None else None
        if predicted_reviews is not None: result["human_review_trigger_recall"]=round(sum(predicted_reviews[i] for i in high)/len(high),3) if high else None
    return result

