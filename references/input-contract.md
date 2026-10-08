# 0.5.2当前输入与交付契约

run-batch接受平台原QuerySpec与授权项，数量1–10；acquire仅数量1，批量拒绝use_run_batch。一次选材队列按已确认排序选择不同ID，数量不足标partial/shortageCount，绝不补位。千川targetTopN=candidateTopN，云图target_top_n≤10且candidate_top_n=1000。每条绑定原请求/共享源SHA/选择与队列SHA，源硬链接不复制报表；任意源变化停止。首条详情CSV必须确认真实、可解析、身份/周期匹配才继续，失败/未知/blocked停止全队列。先串行完成全部选中素材的A详情校验/下载，再按原顺序串行B；A失败不启动CV，B失败保留全部A和已完成B。batch.json区分stage、acquiredCount、completedCount与逐条acquisitionStatus/cvStatus。授权、日期、字段语义沿用以下既有契约。

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

## 0.5.2尺寸与状态反馈

源视频长边≤1936（1920+16），总像素≤3,686,400，不扩大原1920×1920最大面积。时长≤180秒、帧率≤60fps、视频≤128MiB及内存阈值保持；原视频不裁剪/转码，CV最大边仍320。尺寸容差仅用于资源准入，身份宽高比较保持精确。config/media-input-policy.json入包，超限media_input_limit保存实际媒体/准入原因与validation=not_run，失败页显示实际值和限制。

status --run-dir支持单条与批次目录。批次读取batch.json并按每条绑定的attemptId汇总各次状态、退出码、清理及镜头数，不查询批次根cv/latest、不混用另一attempt；返回mode=batch、stage、requested/selected/acquired/completedCount、cv.status/各状态计数/shotCount及entries。批次成功与CV成功分别表达，导出失败可batch failed但cv succeeded；素材短缺可batch partial但选中CV succeeded。终态缺收据/状态不确认记unconfirmed，运行中退出记interrupted（旧批次无PID则不推断队列进程）；查询只读元数据，不重新核验全部媒体/帧SHA或触发RPA/CV/恢复。旧0.5.1批次兼容，单条原status契约保持。
