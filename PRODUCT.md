# CV 分镜报告产品

## Register

product

## Users

千川与云图素材运营、脚本复盘同事。一次查询选择少量素材，逐镜头查看画面和节奏。

## Product Purpose

用一份可离线分享的 HTML 呈现已完成的 CV 结果；素材可切换、每个镜头可定位并查看代表帧。数据来源和执行诊断可追溯。

## Brand Personality

清晰、克制、便于核对。遵循用户确认的业务工作台方向，并参考现有千川云图元技能与脚本工作台的素材列表、详情区和折叠证据结构。

## Anti-references

避免主页面铺满原始 JSON、代码块或文件路径，避免技术参数淹没业务画面。

## Design Principles

- 代表帧和镜头节奏优先。
- 素材范围、完成状态和未执行缺口可见。
- 算法事实与人工质量判断分别表达。
- 一份轻量 HTML 可离线阅读，原始证据留在运行目录。

## Accessibility & Inclusion

中文系统字体；正文对比度至少 4.5:1；键盘焦点、明确按钮标签；手机布局和打印兼容；无需动画或网络资源。

## 0.5.4内存释放与统一交付

批量路径的A和B只保存可恢复的输入、镜头/帧、状态与收据，不逐条渲染index.html或组装ZIP。每条B完成进程组清理和完整校验后，保存绑定该attempt的小report JSON/receipt快照，batch.json冻结快照SHA；写完镜头摘要后，对该条A输入、本次attempt收据列出的帧/日志及快照执行显式文件缓存建议与Python gc.collect，再启动下一条。A全部就绪后丢弃已落盘的完整选材/queue Python对象，保留queue.json和全部源文件。

默认到队列结束才生成一份统一HTML；普通失败停队列后可汇总已成功、失败与pending，pending不混用该A目录历史latest成功attempt。守卫/阶段余量不足或进程清理不确认时不强行补生成报告；即使外层队列尚未锁存，也依据本次attempt的失败收据保存guardStopReason与来源，后续项仍pending。显式--delivery audit也等全部CV完成后才逐条组装证据ZIP，以冻结快照核对各自attempt；普通单条acquire/probe-cv/render-report保持原HTML入口。

大MP4/CSV及已绑定选材源的完整SHA核验保留，使用显式自有普通文件的1MiB有界流式读取：一次fsync，读完的完整页逐块POSIX_FADV_DONTNEED，EOF建议包含末尾不足一页的部分；核对初末文件身份/大小/修改时间和完整已读字节。worker解码前、监督器完成后及输入复验均记录cache-advice.ndjson中的operation、hashedBytes、sha256、supported/errors与前后cgroup观测。FFmpeg可执行文件/依赖仍使用普通摘要，不清全局二进制缓存；拒绝文件、内部路径和owner根软链接。最终快照校验不读CSV/MP4。

HTML使用可重复迭代器：第一遍逐条核验只保留素材导航与计数，第二遍再次校验同一冻结SHA后逐条写镜头和有界JPEG，读取结束在finally建议释放该快照/帧，异常也关闭迭代器。不在Python中保留全批报告/镜头列表；图片预算仍12MiB、单帧256KiB。缓存建议、GC和进程退出分别记录，它们都不保证腾出指定容量或避免瞬时OOM；80%工作集、95%原始占用、256MiB进程树守卫及原输入门禁保持。真实1GiB沙箱多素材与稳定性、镜头人工质量仍待验收。

## 0.5.5高缓存基线的准入复核

本版修正v1统计缺字段导致在RPA之前误把全部缓存算作工作集的路径。v1原生Linux的inactive_file是file LRU，不含tmpfs/shmem；缺失shmem仍如实保留missing字段，不填0，也不再次从file LRU扣除。dirty/writeback先用同层字段；任意原文total_*出现即固定total层级，坏值/重复/缺失的total字段不能降到local。只有缺少dirty/writeback时，才用只读原生/proc/meminfo前后两次Dirty/Writeback的较大值作全局观测上界代理。该来源独立记录nativeProcMeminfo、两点时间、原两行和各扣项来源，不伪装成cgroup字段；严格核验/proc挂载、覆盖/软链接、kB单位、非负值、重复与缺字段，失败保持raw回退。两点观测与内核统计非原子，不能保证整个间隔或未来的可回收容量。

80%工作集、95%原始占用、256MiB进程树及原阶段reserve数值保持。95%的语义由无条件停止变为缓存支持的准入复核：仅v1有可靠正抵扣、工作集低于80%、阶段余量和树预算足、当前及固定baseline的failcnt有效且无增量、under_oom明确为0时，才可继续；PSI缺失保留unknown，full avg10≥1或可读full.total新增压力均否决高raw特例。RSS未知、扣项证据不可靠、当前OOM、计数异常/增量都不能放行；raw达到内核额度始终停止。v2高raw95保持直接保护，不适用v1特例。该版本改变了95%的准入政策，不能描述为守卫策略完全不变。

阶段预留使用保守工作集估计到80%停止线及95%线的较小余量，树预算还需256MiB减已知树RSS≥原reserve；无正抵扣时保留raw余量再与80%线余量取小。新增headroomForStageBytes/headroomBasis/processTreeHeadroomBytes；原headroomToSkillRawCeilingBytes保持真实raw值，不能因缓存估计伪造。固定启动baseline供Resources和整队列监测持续比较，不逐次重置历史failcnt/压力；guard标policyVersion=0.5.5-cache-backed-admission及rawCeilingExceeded/cacheBackedAdmission。可读统计仍非空闲内存或无OOM保证。

0.5.4的逐条落盘、显式自有文件缓存建议与GC、进程清理、冻结attempt/SHA快照、最终统一HTML及审计后置继续保留。并发、输入身份/周期、媒体尺寸、算法、依赖与交付布局不变。新增本地回归复现两组日志参考基线，并显式补入人工构造的可信upper/under_oom证据以验证HTTP选材、详情POST、A+B及最终HTML；日志原缺证据和脏缓存/压力失败仍停止。这些测试不证明实际沙箱已经可用或免于OOM。
