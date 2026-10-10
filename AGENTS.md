# yuntu-cv-shot-probe

本仓独立维护沙箱样本。修改前读 SKILL.md、README、packaging.json 和项目管理现行设计。
- 0.5.5守卫：v1 file LRU排除shmem，dirty/writeback缺失仅独立可信native-proc全局观测代理可补；95%为严格缓存准入复核而非无条件停止，原80/95/256和reserve数值不变但语义改变。阶段预留覆盖80%软线/树预算；raw到额度或当前OOM/新failcnt/压力/未知证据仍停，固定baseline不重置。
- 当前A取视频+B低内存CV；不引入ASR/OCR/模型分析。CV必须复用A已校验输入，由独立受监督worker执行。
- 迁移实现按 migration/source-manifest.json 维护，不能运行时导入兄弟仓。
- 测试用 python3.12 -B tools/test.py；打包用 python3.12 -B tools/build.py。
- 保留动态契约、授权、CSV/身份/周期门禁；run-batch一次榜单选1–10条不同素材，先每批最多3条详情RPA、收齐CSV并串行下载/核验视频，全部A就绪后串行B分镜，无补位/自动重提；acquire单条保留，probe-cv-batch复用显式已有A。默认只交付可视化HTML，完整ZIP仅显式审计。
- 批量A/B内部_defer_report只落盘必要数据，B完成后小JSON快照冻结attempt/SHA、receipt核验和资源摘要后release_item再下一条；全部队列结束才HTML，显式审计也后置。memory/phase守卫或cleanup未确认禁止补报告；不提高阈值。
- 自有MP4/CSV完整SHA用页对齐有界digest_owned并记录建议，不能作用依赖二进制/全局缓存；快照/帧用repeatable factory逐条核验释放，不能聚集全批report对象。
- 来源/输出均在仓外，媒体、凭证、运行数据、环境不进入 Git/ZIP。
- 每次优化同步项目管理的唯一进度与总规划；提交/推送/发布按当前授权。

- 0.5.6产物：新运行默认当前工作对象目录/云图素材分镜数据/唯一run子目录；output-root自动分运行、output-dir精确新目录互斥，返回绝对runDir。resume/单独导出显式原目录或目标路径；不移动旧产物，来源/输出仍在仓外。
