from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
labels={
"forced_or_unexpected_jump":("点击后自动跳转到陌生页面","high"),
"malicious_or_suspicious_redirect":("页面提示病毒并诱导跳转到可疑链接","critical"),
"misleading_claim":("文案写着稳赚100%且无需任何条件","medium"),
"vulgar_or_inappropriate_content":("素材含低俗擦边内容，让人不适","high"),
"excessive_ad_frequency":("广告太多，一直弹出影响使用","medium"),
"repetitive_material":("同一广告和素材重复出现，已经看腻","medium"),
"unclear_material":("画面模糊，小字完全看不清","medium"),
"stale_material":("还是去年的旧活动，日期已经过期","medium"),
"weak_first_three_seconds":("视频前三秒只有空镜，开场拖沓","medium"),
"irrelevant_targeting":("这个内容与当前天气场景完全无关","medium"),
"return_path_friction":("进入后要连续返回很多次，还是回不去原页面","high"),
"potential_privacy_risk":("一打开就要求通讯录和定位权限，担心隐私","critical"),
}
industries=["游戏","电商","金融","工具","内容","教育","医疗","其他"]
media=["锁屏","负一屏/智慧桌面","天气","浏览器","视频","其他"]
landing=["Web","浏览器详情页","Deeplink","应用下载","快应用","其他"]
formats=["图片","横版视频","竖版视频","图文"]
records=[]; idx=1
for label,(feedback,risk) in labels.items():
    for n in range(8):
        other=None
        if n<2:
            keys=list(labels); other=keys[(keys.index(label)+1)%len(keys)]
        combined=feedback+("；"+labels[other][0] if other else "")
        gold=[label]+([other] if other else [])
        gold_risk="critical" if any(labels[x][1]=="critical" for x in gold) else "high" if any(labels[x][1]=="high" for x in gold) else "medium"
        records.append({"record_id":f"S{idx:03d}","split":"evaluation" if n<6 else "demo","input":{"title":f"合成演示素材 {idx}","ad_copy":"公开演示文案，不代表真实投放","feedback":combined,"industry":industries[idx%len(industries)],"media_scene":media[idx%len(media)],"landing_type":landing[idx%len(landing)],"material_format":formats[idx%len(formats)],"first_three_seconds":"前三秒信息正常" if "weak" not in label else feedback},"gold_labels":gold,"gold_risk":gold_risk,"rationale":"依据合成反馈中的明确关键词进行人工黄金标注。","boundary_case":False}); idx+=1
for n in range(10):
    records.append({"record_id":f"S{idx:03d}","split":"evaluation" if n<8 else "demo","input":{"title":f"合成正常素材 {idx}","ad_copy":"展示商品名称、价格和适用条件","feedback":"页面打开和返回都正常，暂未发现明确问题","industry":industries[idx%8],"media_scene":media[idx%6],"landing_type":landing[idx%6],"material_format":formats[idx%4],"first_three_seconds":"开场直接展示主要信息"},"gold_labels":["no_issue"],"gold_risk":"low","rationale":"未发现明确问题，但不等于通过法务审核。","boundary_case":False}); idx+=1
boundaries=["感觉有点奇怪，但说不清哪里有问题","好像见过这条，也可能只是风格相似","点击以后页面变化了，不确定是不是我误触","内容一般，没有特别喜欢","字有一点小但仍能阅读","开头比较慢，也可能是叙事需要","这个广告对别人可能有用","返回了一次就回来了，但动画有点慢","需要定位来提供天气，权限用途看起来相关","宣传很好，但没有看到绝对化承诺"]
for text in boundaries:
    records.append({"record_id":f"S{idx:03d}","split":"demo","input":{"title":f"合成边界素材 {idx}","ad_copy":"演示文案","feedback":text,"industry":industries[idx%8],"media_scene":media[idx%6],"landing_type":landing[idx%6],"material_format":formats[idx%4],"first_three_seconds":"信息不足"},"gold_labels":["no_issue"],"gold_risk":"low","rationale":"反馈模糊，证据不足，黄金标签采用 no_issue 并要求保留不确定性。","boundary_case":True}); idx+=1
assert len(records)>=100
(ROOT/"data").mkdir(exist_ok=True)
(ROOT/"data"/"synthetic_records.json").write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8")
print(len(records))
