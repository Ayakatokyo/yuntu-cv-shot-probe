# 0.5.5当前输入与交付契约

## 0.5.6产物目录契约（2026-10-08）

新运行CLI（run-batch/probe-cv-batch/acquire）默认使用调用方当前工作对象目录下的 `云图素材分镜数据/run-<UTC时间>-<8位随机标识>/`。`--output-root` 为自动分运行的数据根目录，`--output-dir` 为精确新目录，两者互斥；拒绝技能目录/软链接与已存在的新运行目录。返回绝对 `runDir`，批次写入batch.json，最终HTML以report.htmlPath为准（批量index.html、单条report/index.html）。resume继续显式指定原目录；已有A仍由清单指定输入并保存新CV attempt，export-html/export-report继续显式指定交付路径。旧产物不移动，算法、身份/SHA、守卫、并发和HTML样式保持。本仓独立实现，不运行时导入其他技能。完整用法见SKILL.md的0.5.6节。

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

run-batch接受平台原QuerySpec与授权项，数量1–10；acquire仅数量1，批量拒绝use_run_batch。一次选材队列按已确认排序选择不同ID，数量不足标partial/shortageCount，绝不补位。千川targetTopN=candidateTopN，云图target_top_n≤10且candidate_top_n=1000。每条绑定原请求/共享源SHA/选择与队列SHA，源硬链接不复制报表；任意源变化停止。首批最多3条详情CSV必须收齐并核验真实、可解析、身份/周期匹配；失败/未知/blocked不提交新批次。先每批最多3条提交详情RPA并核验本批CSV、串行下载/核验视频，全部批次A就绪，再按原顺序串行B；A失败不启动CV，B失败保留全部A和已完成B。batch.json区分stage、acquiredCount、completedCount与逐条acquisitionStatus/cvStatus。授权、日期、字段语义沿用以下既有契约。

默认交付内嵌代表帧的单HTML；export-html校验已完成report.json快照收据及CV收据/镜头/帧，不读CSV或MP4，不具备重新验证完整A能力；完整A审计仍用verify，视频输入使用probe-cv时仍全验证。未提供完整A输入不能从HTML恢复B。旧export-report为显式审计大包选项，不能因为默认只有HTML称交付缺视频。旧节中“必须完整ZIP”为历史技术包规则，默认已由本节替代。

# 输入与恢复契约

request.json 包含 query_spec 及所选授权 ID；使用 config/request-example.json 的结构，示例日期需按本次用户输入替换。字段注册表来自本包config，不用另装元技能。

云图：rpa_shop。query_spec沿用云图元技能；collection.target_top_n为1–10，candidate_top_n固定1000。多选筛选编码由程序转为实时连接器要求的字符串。

元技能的完整日期、筛选/排序语义沿用；样本取消高光规则，只准备输入。CLI acquire 涉及授权线上取数，validate/status/verify/render-report为本地操作。未知状态只检查既有task ID；resume是用户明确恢复后的入口，不自动调用。

输出：request/environment/status JSON，acquisition任务/CSV/选材/来源/收据，media原视频与下载收据，resources.ndjson和report完整技术报告。原CSV/签名URL保留私有；报告不显示账号URL或凭证。视频最大128MiB，CSV/报表文件32MiB，时长≤180秒，长边≤1936且总像素≤3,686,400，帧率≤60。超限终止不换素材。CSV有身份和周期但缺URL归为视频来源缺口，不误报为入参CSV无效。

A阶段资源记录为当前Python进程RSS/生命周期高水位、Linux进程树采样及可见cgroup指标；一秒采样可能遗漏短时峰值，历史memory.peak不代表本次峰值。macOS无Linux cgroup时记录不可用，不伪造容器额度。阶段完成为video_ready，A完成时CV标not_run，B结果独立记录。

0.1.1补充：preflight不需HTTP依赖即可给缺依赖短状态；先在同一Python环境安装依赖，再validate/acquire。media/probe.json在身份辅助比较之前落盘，失败报告可显示实测值和比较容差，status仍failed。整数秒元数据±1秒，小数秒0.1秒，维度/FPS严格，时长0代表缺失。成功receipt按相对路径去重。

export-report生成仓外独立目录和同名ZIP，含report、合法下载视频、resources.ndjson及bundle-manifest；verify-export校验完整文件集合、资源引用与哈希。原CSV/URL/请求不导出。实际下载ZIP若只有report即不完整，不能用于CV输入或内存原始采样核查。activeSampledSec汇总同执行的连续采样段，不把resume间隔当活跃耗时；elapsedObservedSec仍表示首尾墙钟跨度。

## 0.4.0恢复与内存补充

阶段启动余量不足返回paused/insufficient_stage_headroom，phase-memory.json/ndjson保留判定，已绑定选择/源文件和tasks不清除。resume需明确用户授权，原request、selection-source哈希和首批CSV门禁仍校验；已有selection.json复用，不重新选材。CSV blocked及未知提交仍禁止自动重提。原始数据及历史检查点不因缓存建议被删除；fsync/DONTNEED只为建议，不承诺腾出沙箱容量。新恢复路径仅在已保存选择后复用选材结果；报表下载失败的人工CSV导入尚无正式CLI，继续保留既有私有恢复证据，不自动重提API。

恢复选择的快捷路径要求0.4.0 selection-binding.json同时绑定原请求、selection-source和selection.json内容；任何变化停止。旧目录缺此绑定时用流式兼容路径重算原选择并比较，不把未绑定的选择文件直接信任为已验证。

## 0.5.3尺寸与状态反馈

源视频长边≤1936（1920+16），总像素≤3,686,400，不扩大原1920×1920最大面积。时长≤180秒、帧率≤60fps、视频≤128MiB及内存阈值保持；原视频不裁剪/转码，CV最大边仍320。尺寸容差仅用于资源准入，身份宽高比较保持精确。config/media-input-policy.json入包，超限media_input_limit保存实际媒体/准入原因与validation=not_run，失败页显示实际值和限制。

status --run-dir支持单条与批次目录。批次读取batch.json并按每条绑定的attemptId汇总各次状态、退出码、清理及镜头数，不查询批次根cv/latest、不混用另一attempt；返回mode=batch、stage、requested/selected/acquired/completedCount、cv.status/各状态计数/shotCount及entries。批次成功与CV成功分别表达，导出失败可batch failed但cv succeeded；素材短缺可batch partial但选中CV succeeded。终态缺收据/状态不确认记unconfirmed，运行中退出记interrupted（旧批次无PID则不推断队列进程）；查询只读元数据，不重新核验全部媒体/帧SHA或触发RPA/CV/恢复。旧0.5.1批次兼容，单条原status契约保持。
