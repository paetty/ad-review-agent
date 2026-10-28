# 规则和数据来源登记

核验日期：2026-10-22。可访问的公开版本不等于最新正式版本。摘要不是官方原文，不能把平台范围泛化到其他平台。

## 当前知识库

原01—07文件为自编synthetic_demo演示规范。新增08—10是基于下列公开一手资料编写的短摘要，content_type=human_summary；11为明确标记的internal_simulated。检索与页面会返回来源类型、链接、发布方、版本、核验时间和平台范围。

1. 国家市场监督管理总局《互联网广告管理办法》2023年第72号令，参考第九至十一条。链接：https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/fgs/art/2023/art_d93a579afd45413e8576e4623fab348f.html 。适用条件需回原文核验；关闭弹窗与返回落地页不能直接混用。
2. vivo官方域名上的《“vivo营销”广告内容审核规范V7.0》，本项目摘要仅概括PDF第3页审核范围。链接：https://ads-marketing-vivofs.vivo.com.cn/NtBrJ9dueygDLoz8/admin/5c391eb7-889f-453f-8c98-8f0ee2ab17ff.pdf 。未确认是最新版本，只有platform=vivo时检索使用。
3. OPPO官方公开《OPPO广告审核规范》，本项目参考通用内容质量相关部分。链接：https://e.oppo.com/marketing/doc/material-feeds.html 。页面未提供明确版本号/生效日期，只有platform=oppo时检索使用。

11号文件的“同主体同素材24小时超过3次触发调查”“准备至少3个轮换素材”等均是为了演示而设的待验证假设，不是法规或任何平台内部策略。没有用户级曝光数据时，本系统不会声称识别真实频次超标。

## 可用外部研究数据

研究项目：Ad Perceptions Dataset / CHI 2021，What Makes a Bad Ad? User Perceptions of Problematic Online Advertising。

仓库：https://github.com/eric-zeng/chi-bad-ads-data 。原始README说明包含500个广告截图和用户观感标注，研究参与者1025人。实际读取元数据确认500个广告，评分CSV有5104行，从可选文字评论整理出813条非空文本候选。每行评分不是一条独立广告；参与者数也不是评论数。

适用：扩展广告素材多样性、用户主观感受分析和英文迁移探索。局限：不是中文移动端反馈金标，不包含本项目12类标签，也没有曝光、点击返回序列；不能直接用于频控验证或报告本项目准确率。

运行 `scripts/inspect_public_ads.py --fetch`，仅获取广告元数据和评分/可选文字，不获取participant_context，不保留参与者ID，不下载截图。整理后仍需人工检查隐私、标注、类别映射和素材授权。许可证及原图再分发权未确认，因此候选仅存本地已忽略的output/public-data，不随本项目MIT开源。

当前不把外部英文评论直接翻译后当中文真值。若后续翻译或重标注，必须保留原来源和翻译记录，且按原广告ID分组隔离，防止同一素材进入开发和盲测两边。

## 合成业务数据与评测数据的不同目的

业务模拟案例验证关联分母、状态流转和报告交接。48条v2候选验证不同表达和失败类型，人工标注尚待完成。外部813条文本用于扩充待标注池。这三者的来源、用途和结果不得混合成一个“大规模真实准确率”。
