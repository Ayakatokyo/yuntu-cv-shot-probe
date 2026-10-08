# 云图 CV 分镜工作台 0.5.5

## 0.5.5高缓存基线的准入复核

本版修正v1统计缺字段导致在RPA之前误把全部缓存算作工作集的路径。v1原生Linux的inactive_file是file LRU，不含tmpfs/shmem；缺失shmem仍如实保留missing字段，不填0，也不再次从file LRU扣除。dirty/writeback先用同层字段；任意原文total_*出现即固定total层级，坏值/重复/缺失的total字段不能降到local。只有缺少dirty/writeback时，才用只读原生/proc/meminfo前后两次Dirty/Writeback的较大值作全局观测上界代理。该来源独立记录nativeProcMeminfo、两点时间、原两行和各扣项来源，不伪装成cgroup字段；严格核验/proc挂载、覆盖/软链接、kB单位、非负值、重复与缺字段，失败保持raw回退。两点观测与内核统计非原子，不能保证整个间隔或未来的可回收容量。

80%工作集、95%原始占用、256MiB进程树及原阶段reserve数值保持。95%的语义由无条件停止变为缓存支持的准入复核：仅v1有可靠正抵扣、工作集低于80%、阶段余量和树预算足、当前及固定baseline的failcnt有效且无增量、under_oom明确为0时，才可继续；PSI缺失保留unknown，full avg10≥1或可读full.total新增压力均否决高raw特例。RSS未知、扣项证据不可靠、当前OOM、计数异常/增量都不能放行；raw达到内核额度始终停止。v2高raw95保持直接保护，不适用v1特例。该版本改变了95%的准入政策，不能描述为守卫策略完全不变。

阶段预留使用保守工作集估计到80%停止线及95%线的较小余量，树预算还需256MiB减已知树RSS≥原reserve；无正抵扣时保留raw余量再与80%线余量取小。新增headroomForStageBytes/headroomBasis/processTreeHeadroomBytes；原headroomToSkillRawCeilingBytes保持真实raw值，不能因缓存估计伪造。固定启动baseline供Resources和整队列监测持续比较，不逐次重置历史failcnt/压力；guard标policyVersion=0.5.5-cache-backed-admission及rawCeilingExceeded/cacheBackedAdmission。可读统计仍非空闲内存或无OOM保证。

0.5.4的逐条落盘、显式自有文件缓存建议与GC、进程清理、冻结attempt/SHA快照、最终统一HTML及审计后置继续保留。并发、输入身份/周期、媒体尺寸、算法、依赖与交付布局不变。新增本地回归复现两组日志参考基线，并显式补入人工构造的可信upper/under_oom证据以验证HTTP选材、详情POST、A+B及最终HTML；日志原缺证据和脏缓存/压力失败仍停止。这些测试不证明实际沙箱已经可用或免于OOM。

## 0.5.4内存释放与统一交付

批量路径的A和B只保存可恢复的输入、镜头/帧、状态与收据，不逐条渲染index.html或组装ZIP。每条B完成进程组清理和完整校验后，保存绑定该attempt的小report JSON/receipt快照，batch.json冻结快照SHA；写完镜头摘要后，对该条A输入、本次attempt收据列出的帧/日志及快照执行显式文件缓存建议与Python gc.collect，再启动下一条。A全部就绪后丢弃已落盘的完整选材/queue Python对象，保留queue.json和全部源文件。

默认到队列结束才生成一份统一HTML；普通失败停队列后可汇总已成功、失败与pending，pending不混用该A目录历史latest成功attempt。守卫/阶段余量不足或进程清理不确认时不强行补生成报告；即使外层队列尚未锁存，也依据本次attempt的失败收据保存guardStopReason与来源，后续项仍pending。显式--delivery audit也等全部CV完成后才逐条组装证据ZIP，以冻结快照核对各自attempt；普通单条acquire/probe-cv/render-report保持原HTML入口。

大MP4/CSV及已绑定选材源的完整SHA核验保留，使用显式自有普通文件的1MiB有界流式读取：一次fsync，读完的完整页逐块POSIX_FADV_DONTNEED，EOF建议包含末尾不足一页的部分；核对初末文件身份/大小/修改时间和完整已读字节。worker解码前、监督器完成后及输入复验均记录cache-advice.ndjson中的operation、hashedBytes、sha256、supported/errors与前后cgroup观测。FFmpeg可执行文件/依赖仍使用普通摘要，不清全局二进制缓存；拒绝文件、内部路径和owner根软链接。最终快照校验不读CSV/MP4。

HTML使用可重复迭代器：第一遍逐条核验只保留素材导航与计数，第二遍再次校验同一冻结SHA后逐条写镜头和有界JPEG，读取结束在finally建议释放该快照/帧，异常也关闭迭代器。不在Python中保留全批报告/镜头列表；图片预算仍12MiB、单帧256KiB。缓存建议、GC和进程退出分别记录，它们都不保证腾出指定容量或避免瞬时OOM；80%工作集、95%原始占用、256MiB进程树守卫及原输入门禁保持。真实1GiB沙箱多素材与稳定性、镜头人工质量仍待验收。

## 0.5.3详情RPA并行批次

参考千川元技能/工作台与云图元技能/工作台的最多3条在途及首批CSV门禁策略。run-batch按既定选材顺序划分每批≤3条：先依次发出本批提交请求并保存各taskId，不等待上一条完成；再按原顺序轮询、下载并核验本批全部CSV；之后串行下载/核验视频，本批成功才提交下一批。RPA远端最多3个在途任务，本地媒体与CV并发仍1；全部批次A就绪才开始串行B。

首批firstBatchCsvGate收齐结果：有未知/未提交结果为unconfirmed，全终态且至少一份有效CSV为passed，全无有效CSV为blocked。CV队列更严格，任一选中素材A失败都不提交新批、不启动B；即使首批gate passed也不能跳过失败素材继续。普通失败继续核实本批已保存taskId的其余任务，保留CSV/任务结果与失败前的有效A输入；不下载首个失败项之后的视频。队列守卫锁存后在提交、轮询、下载块及阶段边界合作停止本地新工作；执行中断保留原任务，保留在途证据，不能称远端任务已取消。未知提交保留submission_intent，不重提；collect/media只能复用已保存任务，缺taskId失败。

batch.json记录rpaConcurrency=3、mediaConcurrency=1、cvConcurrency=1（旧concurrency=1仍指CV）、rpaSubmissionCount、rpaWaves、acquisitionPhase与逐条rpaWave/rpaStatus/taskId；提交计数只计已确认taskId，未知请求不算确认成功。视频仍原SHA/有界尺寸/严格身份，CSV缓存绑定与哈希复验不放宽。数量1/短缺/最后不足3条按实际条数提交，不滚动补位、不重抓榜单、不自动重试或恢复。

独立源码：yuntu-cv-shot-probe。0.5.5支持一次提问处理1–10条不同素材，一次榜单选材后先每批最多3条提交详情RPA并收齐CSV，串行完成视频下载/核验，再逐个执行CV并确认进程清理，默认一份可离线HTML。元技能/脚本工作台仅作设计参照，不运行时导入其代码，不改变这四个仓或插件。

入口见[SKILL.md](SKILL.md)。新取数run-batch、已有A串行probe-cv-batch、已有B轻量交付export-html；完整export-report ZIP仍是显式审计选项。现有详情素材数就是CV批量数量（不新增字段）；表单/pre_input数量范围、授权ID说明、默认交付同步。素材不足如实partial，失败停队列，pending保留，不自动恢复或补位。

HTML采用素材导航、大幅代表帧、原时间区间比例时间轴、完整镜头画廊、时长筛选、折叠执行摘要。JPEG单张256KiB、全报告12MiB预算，逐帧标明超限缺口；不嵌入视频、CSV、账号、签名URL或原始日志。导出校验已完成报告快照与CV镜头帧，避免重复读大媒体；原输入留运行目录可复验。

内存保护使用工作集80%、原始95%缓存准入复核和进程树256MiB；阶段预留还覆盖80%软停止线及树预算。v1缺dirty/writeback仅可信native-proc观测代理可补，其余不可用统计raw回退。约200ms队列/HTML观察和自身文件缓存建议不保证无瞬时OOM。CV原生方案、无ASR或模型分析。源榜单硬链接共享并哈希绑定，避免每条复制大报表。

开发验证：python3.12 -B tools/test.py；最小依赖python3.12 -B tools/test_native.py --require-minimal；显式packaging.json打包python3.12 -B tools/build.py。PRODUCT.md/DESIGN.md为源码设计上下文，不进入运行包。源码/包/平台验收分别记录于项目管理唯一进度。

## 0.5.3尺寸与状态反馈

源视频长边≤1936（1920+16），总像素≤3,686,400，不扩大原1920×1920最大面积。时长≤180秒、帧率≤60fps、视频≤128MiB及内存阈值保持；原视频不裁剪/转码，CV最大边仍320。尺寸容差仅用于资源准入，身份宽高比较保持精确。config/media-input-policy.json入包，超限media_input_limit保存实际媒体/准入原因与validation=not_run，失败页显示实际值和限制。

status --run-dir支持单条与批次目录。批次读取batch.json并按每条绑定的attemptId汇总各次状态、退出码、清理及镜头数，不查询批次根cv/latest、不混用另一attempt；返回mode=batch、stage、requested/selected/acquired/completedCount、cv.status/各状态计数/shotCount及entries。批次成功与CV成功分别表达，导出失败可batch failed但cv succeeded；素材短缺可batch partial但选中CV succeeded。终态缺收据/状态不确认记unconfirmed，运行中退出记interrupted（旧批次无PID则不推断队列进程）；查询只读元数据，不重新核验全部媒体/帧SHA或触发RPA/CV/恢复。旧0.5.1批次兼容，单条原status契约保持。
