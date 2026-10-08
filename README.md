# 云图 CV 分镜工作台 0.5.2

独立源码：yuntu-cv-shot-probe。0.5.2支持一次提问处理1–10条不同素材，一次榜单选材后先逐条完成全部详情CSV校验和视频下载，再逐个执行CV并确认进程清理，默认一份可离线HTML。元技能/脚本工作台仅作设计参照，不运行时导入其代码，不改变这四个仓或插件。

入口见[SKILL.md](SKILL.md)。新取数run-batch、已有A串行probe-cv-batch、已有B轻量交付export-html；完整export-report ZIP仍是显式审计选项。现有详情素材数就是CV批量数量（不新增字段）；表单/pre_input数量范围、授权ID说明、默认交付同步。素材不足如实partial，失败停队列，pending保留，不自动恢复或补位。

HTML采用素材导航、大幅代表帧、原时间区间比例时间轴、完整镜头画廊、时长筛选、折叠执行摘要。JPEG单张256KiB、全报告12MiB预算，逐帧标明超限缺口；不嵌入视频、CSV、账号、签名URL或原始日志。导出校验已完成报告快照与CV镜头帧，避免重复读大媒体；原输入留运行目录可复验。

内存保护保持工作集80%/原始95%/进程树256MiB和阶段余量；扣减字段缺失raw回退。约200ms队列/HTML观察和自身文件缓存建议不保证无瞬时OOM。CV原生方案、无ASR或模型分析。源榜单硬链接共享并哈希绑定，避免每条复制大报表。

开发验证：python3.12 -B tools/test.py；最小依赖python3.12 -B tools/test_native.py --require-minimal；显式packaging.json打包python3.12 -B tools/build.py。PRODUCT.md/DESIGN.md为源码设计上下文，不进入运行包。源码/包/平台验收分别记录于项目管理唯一进度。

## 0.5.2尺寸与状态反馈

源视频长边≤1936（1920+16），总像素≤3,686,400，不扩大原1920×1920最大面积。时长≤180秒、帧率≤60fps、视频≤128MiB及内存阈值保持；原视频不裁剪/转码，CV最大边仍320。尺寸容差仅用于资源准入，身份宽高比较保持精确。config/media-input-policy.json入包，超限media_input_limit保存实际媒体/准入原因与validation=not_run，失败页显示实际值和限制。

status --run-dir支持单条与批次目录。批次读取batch.json并按每条绑定的attemptId汇总各次状态、退出码、清理及镜头数，不查询批次根cv/latest、不混用另一attempt；返回mode=batch、stage、requested/selected/acquired/completedCount、cv.status/各状态计数/shotCount及entries。批次成功与CV成功分别表达，导出失败可batch failed但cv succeeded；素材短缺可batch partial但选中CV succeeded。终态缺收据/状态不确认记unconfirmed，运行中退出记interrupted（旧批次无PID则不推断队列进程）；查询只读元数据，不重新核验全部媒体/帧SHA或触发RPA/CV/恢复。旧0.5.1批次兼容，单条原status契约保持。
