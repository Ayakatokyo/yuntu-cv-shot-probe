---
name: yuntu-cv-shot-probe
description: 从云图素材榜单选择1–10条不同素材，先完成全部详情数据校验和视频下载，再逐个完成低内存镜头切分，交付内嵌代表帧的可视化报告。不进行音频转写或模型分析。
metadata:
  argument_hint: 选择授权账号、日期、素材数量和筛选条件，一次提问完成分镜。
---

# 云图视频CV分镜工作台（0.5.4）

默认先全部A、再串行B：一次查询素材榜单，按筛选排序选择1–10条不同素材，先每批最多3条提交详情RPA，收齐本批CSV并核对身份/周期，再串行下载视频；所有选中素材的A输入就绪后，再按原顺序逐个执行低内存CV分镜并确认进程清理。只交付一份可视化HTML。音频转写、脚本时间码对齐和宿主AI二次分析后置。

## 0.5.4内存释放与统一交付

批量路径的A和B只保存可恢复的输入、镜头/帧、状态与收据，不逐条渲染index.html或组装ZIP。每条B完成进程组清理和完整校验后，保存绑定该attempt的小report JSON/receipt快照，batch.json冻结快照SHA；写完镜头摘要后，对该条A输入、本次attempt收据列出的帧/日志及快照执行显式文件缓存建议与Python gc.collect，再启动下一条。A全部就绪后丢弃已落盘的完整选材/queue Python对象，保留queue.json和全部源文件。

默认到队列结束才生成一份统一HTML；普通失败停队列后可汇总已成功、失败与pending，pending不混用该A目录历史latest成功attempt。守卫/阶段余量不足或进程清理不确认时不强行补生成报告；即使外层队列尚未锁存，也依据本次attempt的失败收据保存guardStopReason与来源，后续项仍pending。显式--delivery audit也等全部CV完成后才逐条组装证据ZIP，以冻结快照核对各自attempt；普通单条acquire/probe-cv/render-report保持原HTML入口。

大MP4/CSV及已绑定选材源的完整SHA核验保留，使用显式自有普通文件的1MiB有界流式读取：一次fsync，读完的完整页逐块POSIX_FADV_DONTNEED，EOF建议包含末尾不足一页的部分；核对初末文件身份/大小/修改时间和完整已读字节。worker解码前、监督器完成后及输入复验均记录cache-advice.ndjson中的operation、hashedBytes、sha256、supported/errors与前后cgroup观测。FFmpeg可执行文件/依赖仍使用普通摘要，不清全局二进制缓存；拒绝文件、内部路径和owner根软链接。最终快照校验不读CSV/MP4。

HTML使用可重复迭代器：第一遍逐条核验只保留素材导航与计数，第二遍再次校验同一冻结SHA后逐条写镜头和有界JPEG，读取结束在finally建议释放该快照/帧，异常也关闭迭代器。不在Python中保留全批报告/镜头列表；图片预算仍12MiB、单帧256KiB。缓存建议、GC和进程退出分别记录，它们都不保证腾出指定容量或避免瞬时OOM；80%工作集、95%原始占用、256MiB进程树守卫及原输入门禁保持。真实1GiB沙箱多素材与稳定性、镜头人工质量仍待验收。

## 0.5.3详情RPA并行批次

参考千川元技能/工作台与云图元技能/工作台的最多3条在途及首批CSV门禁策略。run-batch按既定选材顺序划分每批≤3条：先依次发出本批提交请求并保存各taskId，不等待上一条完成；再按原顺序轮询、下载并核验本批全部CSV；之后串行下载/核验视频，本批成功才提交下一批。RPA远端最多3个在途任务，本地媒体与CV并发仍1；全部批次A就绪才开始串行B。

首批firstBatchCsvGate收齐结果：有未知/未提交结果为unconfirmed，全终态且至少一份有效CSV为passed，全无有效CSV为blocked。CV队列更严格，任一选中素材A失败都不提交新批、不启动B；即使首批gate passed也不能跳过失败素材继续。普通失败继续核实本批已保存taskId的其余任务，保留CSV/任务结果与失败前的有效A输入；不下载首个失败项之后的视频。队列守卫锁存后在提交、轮询、下载块及阶段边界合作停止本地新工作；执行中断保留原任务，保留在途证据，不能称远端任务已取消。未知提交保留submission_intent，不重提；collect/media只能复用已保存任务，缺taskId失败。

batch.json记录rpaConcurrency=3、mediaConcurrency=1、cvConcurrency=1（旧concurrency=1仍指CV）、rpaSubmissionCount、rpaWaves、acquisitionPhase与逐条rpaWave/rpaStatus/taskId；提交计数只计已确认taskId，未知请求不算确认成功。视频仍原SHA/有界尺寸/严格身份，CSV缓存绑定与哈希复验不放宽。数量1/短缺/最后不足3条按实际条数提交，不滚动补位、不重抓榜单、不自动重试或恢复。

## 输入与单次提问

按metadata.yaml读取授权表单，授权值使用extra.shop_id，不猜账号或历史凭证。日期北京时间T+4；行业、榜单、人群与品牌遵守当前QuerySpec。ALL_INDUSTRY时品牌留空，可选筛选留空就不筛选，不把表单占位提示当有效值。

现有“详情素材数”（detail_top_n）直接控制完整CV分镜批量，写入collection.target_top_n，不新增第二个数量参数。用户明确要求“3条素材”时写入3，不能降成1条。默认1条、范围1–10；超过10条说明单次上限，等待用户选定分批范围，不能静默截断。自然语言筛选转为本包注册表支持的条件，不明确则先澄清。默认rank升序，candidate_top_n固定1000；target_top_n为1–10。契约与示例见[输入契约](references/input-contract.md)。

保持PWD，在用户工作对象目录写request.json，用安装根SKILL_ROOT定位本包脚本。依赖使用宿主既有Python环境与requirements.txt；缺依赖用已有依赖工具同环境binary-only安装，不安装模型。鉴权只用注入环境，不写入命令/日志/请求。外层执行超时留足完整队列（1条至少3600秒，批量按条数留足或分批），不因轮询快速结束把轮询耗时当业务耗时。预检与校验只做一次：

```bash
python "$SKILL_ROOT/scripts/run.py" preflight --cv
python "$SKILL_ROOT/scripts/run.py" validate --request-file "$WORKSPACE_ROOT/request.json"
python "$SKILL_ROOT/scripts/run.py" run-batch --request-file "$WORKSPACE_ROOT/request.json" --output-dir "$WORKSPACE_ROOT/云图分镜-唯一标识"
```

run-batch包含选材、A、B和轻量交付；数量1也用此入口。榜单仅一次，不能循环调用相同TOP1凑数量。每条详情CSV必须通过身份/周期校验，视频媒体辅助身份匹配后才记A就绪；全部A成功后才进入B，取数/下载和CV不会交替；B原生ffmpeg-scene、独立受监督worker、并发1，每条清理完成才下一条。同一沙箱两个平台也不得同时启动队列。用户已要求处理指定条数即可执行，不在每条之间重复询问确认。

## 输出与失败

status --run-dir支持单条与批次目录。批次读取batch.json并按每条绑定的attemptId汇总各次状态、退出码、清理及镜头数，不查询批次根cv/latest、不混用另一attempt；返回mode=batch、stage、requested/selected/acquired/completedCount、cv.status/各状态计数/shotCount及entries。批次成功与CV成功分别表达，导出失败可batch failed但cv succeeded；素材短缺可batch partial但选中CV succeeded。终态缺收据/状态不确认记unconfirmed，运行中退出记interrupted（旧批次无PID则不推断队列进程）；查询只读元数据，不重新核验全部媒体/帧SHA或触发RPA/CV/恢复。旧0.5.1批次兼容，单条原status契约保持。

run-batch或probe-cv-batch结束后，对本次批次目录查询一次status，依据批次status和cv汇总分别反馈整体交付与分镜结果，同时给出CV完成数/选中数和镜头总数。查询失败或unconfirmed时保留诊断，不把未知结果描述为完成，也不据此重跑CV。

```bash
python "$SKILL_ROOT/scripts/run.py" status --run-dir "$BATCH_ROOT"
```

默认交付返回的report.htmlPath及大小/哈希，一份自包含HTML可离线打开，内嵌代表帧，支持素材切换、镜头时间轴、大图、键盘切换和时长筛选。源视频/CSV/账号/签名URL/逐条日志留原运行目录，不使用报告归档器把整个目录打成大ZIP，不导出A中间技术包。CV只产生候选边界，人工质量待核对，不编造画面/口播/效果归因。图片预算12MiB、单张256KiB，超过预算逐帧显示缺口，镜头区间保持完整。

batch.json保存stage（selection/acquisition/cv/delivery/complete）、requestedCount/selectedCount/acquiredCount/completedCount和逐条acquisitionStatus/cvStatus、独立runDir/attempt、worker退出及清理、distinctVideoCount、整队列观测。素材不足返回partial/shortageCount，按实际选中数量执行，不能重新抓榜单或自动补位；重复视频哈希只能证明不同素材可能引用同视频，不能称多视频质量验收。A阶段首次失败停止新批次提交且不启动任何CV；普通失败继续核实当前批已保存任务，守卫/中断停止本地新工作，已就绪A的cvStatus仍pending；B阶段首次失败停止后续CV，全部A输入与已完成B保留，未处理B为pending；保留完成结果和诊断，不自动重试/恢复、重提未知任务或提高阈值。首批CSV blocked不得清除；未知提交只检查原taskId。

单条acquire保留为调试A入口且只接受数量1；批量输入会报use_run_batch，防止静默只取首条。resume仅用户明确恢复时复用原任务/请求/源哈希/绑定选择；队列无自动续跑CLI，不能换目录重取全部以绕过失败。导出失败但B已完成时优先以下轻量导出，不重跑B：

```bash
python "$SKILL_ROOT/scripts/run.py" export-html --run-dir "$RUN_ROOT" --output-file "$WORKSPACE_ROOT/交付/云图分镜-唯一标识.html"
```

export-html核对已生成报告快照、CV收据与镜头/代表帧SHA，不重新读取CSV/MP4或取数；旧报告快照若缺失或已改变须先inspect/render-report，不能伪造收据。运行目录html-exports保留约200ms采样、守卫和导出收据，默认不另给证据ZIP。高基线导致连轻量导出也被拦截时交付已保存诊断并停止。

## 复用已有A与审计选项

已有完整A输入、不需新榜单时用显式清单；缺视频的报告ZIP不是A输入。1–10项，每条只含完整A绝对runDir；重复同A用于稳定性时每条生成新attempt，独立快照绑定该次结果，不把B缓存复用算多次执行。

```json
{"schemaVersion":1,"runs":[{"runDir":"/绝对路径/完整A目录"}]}
```

```bash
python "$SKILL_ROOT/scripts/run.py" probe-cv-batch --manifest-file "$WORKSPACE_ROOT/已有输入.json" --output-dir "$WORKSPACE_ROOT/串行分镜-唯一标识"
```

默认最终只交付一份HTML。仅用户明确要求完整视频/内存审计证据时，probe-cv-batch可加--delivery audit，或调用export-report --run-dir --output-dir及verify-export --bundle-dir；审计ZIP包含MP4、A/B日志、全部帧、独立导出内存证据ZIP，可能再次触及缓存保护线，不能为了交付提高阈值。

## 资源保护与质量边界

源视频长边≤1936（1920+16），总像素≤3,686,400，不扩大原1920×1920最大面积。时长≤180秒、帧率≤60fps、视频≤128MiB及内存阈值保持；原视频不裁剪/转码，CV最大边仍320。尺寸容差仅用于资源准入，身份宽高比较保持精确。config/media-input-policy.json入包，超限media_input_limit保存实际媒体/准入原因与validation=not_run，失败页显示实际值和限制。

不安装NumPy/OpenCV/PySceneDetect等重型CV依赖；仅明确算法对照才binary-only安装requirements-cv.txt并显式adaptive。默认FFmpeg单线程、最大边320、原PTS、每镜头代表帧、最多300镜头，超限/缺帧失败不整段回退。工作集80%、原始占用95%、进程树256MiB以及压力/事件保护保持；扣减shmem/dirty/writeback任一同层字段缺失则raw保守回退，额度/压力不可读保持未知。阶段余量见config/memory-policy.json。

采样约200ms仍可能漏瞬时峰值，不保证绝不OOM。只有本次完成的显式普通文件尝试fsync/DONTNEED建议，不删源文件、不清全局缓存，不承诺腾出指定内存。批量选材源通过硬链接共享，不复制大榜单，绑定请求/源/每条选择，源变化会使所有依赖输入校验失败。三次稳定性、真实多素材及人工质量仍需平台证据；本地合成和HTML重绘不等于平台验收。详见[CV契约](references/cv-contract.md)。
