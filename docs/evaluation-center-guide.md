# 统一评测中心

开发集是练习题，用于发现错误、修改规则和Prompt后回归。验证集用于阶段性比较；如果反复按它调整系统，就不能再称为独立验证。当前四套均为合成数据，不是企业真实数据或独立盲测。

## 页面操作

1. 打开“评测中心”，选择新版开发集28条、新版验证集8条、补充开发集12条或旧版回归集80条。条数从数据文件实时读取。留出候选不开放。
2. 选择规则基线（无模型API调用）或真实模型+规则+当前TF-IDF RAG。这里的选择不修改其他分析页面模式。
3. 点击预览，查看案例数、预计逻辑调用次数、最多HTTP尝试数与模型配置。真实费用未定价，保持未知。
4. 真实模式需要勾选确认调用量及费用，再开始。不会因进入页面自动调用模型。
5. 查看进度和逐条对比；可仅显示不符合参考或调用失败。旧80条没有明确状态参考，不计状态匹配；显示各适用项是否同时符合，而不伪称所有都是四项。
6. 历史记录可再次打开。结果写evaluation_runs和evaluation_items，不写业务analyses，不进入业务量看板。运行时使用固定Prompt快照和隔离分析会话；单次运行内不更新Prompt。

## 脚本统一入口

在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe scripts/run_evaluation.py --dataset development --mode rules
.\.venv\Scripts\python.exe scripts/run_evaluation.py --dataset validation --mode rules
.\.venv\Scripts\python.exe scripts/run_evaluation.py --dataset supplement --mode rules
.\.venv\Scripts\python.exe scripts/run_evaluation.py --dataset legacy --mode rules
.\.venv\Scripts\python.exe scripts/run_evaluation.py --dataset supplement --mode provider --preview
```

确认后真实运行需额外加--allow-provider。脚本和页面使用相同数据加载器及执行器，产物保存output/evaluation/run-ID-UTC时间戳.json，避免不同隔离数据库的同号记录相互覆盖。原evaluate_v2.py保留历史拆分与留出门禁用途；此前聊天工作目录下的evaluate_supplement.py是历史实验脚本，不再作为推荐入口，其历史报告不覆盖。

## 数据与运行边界

- 48条源文件：data/evaluation/feedback-candidates-v2.json，按split选择28开发或8验证；验证集主要为正常及否定表达，不覆盖完整标签。
- 12条补充源文件：data/evaluation/supplement-12-reviewed-2026-10-27.json。
- 80条旧回归：data/synthetic_records.json的evaluation拆分。
- 数据SHA-256写入预览与记录，启动前文件变化必须重新预览。预览冻结的是数据版本，不代表标注独立。
- 真实调用通常每条一次，超时/限流最多三次HTTP尝试，不能承诺精确费用或总时长。Token来自成功返回，失败用量可能未知。
- 调用失败显示错误码并计入分母（预测为空、风险未识别），不因删除失败项美化结果。高风险Recall按风险等级计算。
- 当前使用本地单进程后台任务，无分布式队列。服务重启将未完成任务标记中断，不自动恢复或重复付费；已完成条目保留。并发运行在本地入口串行限制，不作为多实例生产锁。
- 宏平均F1按全部13类计算，未出现类可能按零处理，应结合support查看。指标不包含建议可执行性的人评。

## 本轮验收（2026-10-28）

- 后端85项测试通过，包括四套条数、模式隔离、数据指纹、真实调用确认、失败不剔除及业务分析表不受污染。
- 前端8项测试、修改文件ESLint、生产构建、2项渲染检查、4项菜单状态保留浏览器检查通过。
- 新增统一评测浏览器联调1项通过：隔离后端实际跑12条规则集，预览0次模型调用、查看逐条差异、切换页面、重复查看历史；真实模式只做预览并验证未勾选时不能运行。
- 统一CLI实际运行8条验证集完成，标签完全匹配6/8、各适用项同时符合5/8，高风险样本0条所以风险Recall为null；这些是当前规则模式的开发结果，不是新模型质量结论。
- 真实模型调用为0；本轮没有为增加分数调整题目、参考答案或规则。
