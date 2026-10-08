# CV 分镜工作台视觉规范

白色背景，浅灰素材导航，蓝色只表达选中项和交互状态；延续千川/云图元技能和脚本工作台的系统字体、素材列表/详情区结构。使用 OKLCH 颜色变量，正文深色、辅助文本不淡化到不可读。左侧可搜索素材列表，右侧大幅代表帧、镜头区间、时长比例时间轴与完整镜头画廊，底部折叠执行来源。900px 单列详情、600px 横向素材导航；打印全部素材画廊。默认不嵌入视频或日志，JPEG 图片总预算 12MiB、单张 256KiB，缺口逐项显示。

## 0.5.4内存释放与统一交付

批量路径的A和B只保存可恢复的输入、镜头/帧、状态与收据，不逐条渲染index.html或组装ZIP。每条B完成进程组清理和完整校验后，保存绑定该attempt的小report JSON/receipt快照，batch.json冻结快照SHA；写完镜头摘要后，对该条A输入、本次attempt收据列出的帧/日志及快照执行显式文件缓存建议与Python gc.collect，再启动下一条。A全部就绪后丢弃已落盘的完整选材/queue Python对象，保留queue.json和全部源文件。

默认到队列结束才生成一份统一HTML；普通失败停队列后可汇总已成功、失败与pending，pending不混用该A目录历史latest成功attempt。守卫/阶段余量不足或进程清理不确认时不强行补生成报告；即使外层队列尚未锁存，也依据本次attempt的失败收据保存guardStopReason与来源，后续项仍pending。显式--delivery audit也等全部CV完成后才逐条组装证据ZIP，以冻结快照核对各自attempt；普通单条acquire/probe-cv/render-report保持原HTML入口。

大MP4/CSV及已绑定选材源的完整SHA核验保留，使用显式自有普通文件的1MiB有界流式读取：一次fsync，读完的完整页逐块POSIX_FADV_DONTNEED，EOF建议包含末尾不足一页的部分；核对初末文件身份/大小/修改时间和完整已读字节。worker解码前、监督器完成后及输入复验均记录cache-advice.ndjson中的operation、hashedBytes、sha256、supported/errors与前后cgroup观测。FFmpeg可执行文件/依赖仍使用普通摘要，不清全局二进制缓存；拒绝文件、内部路径和owner根软链接。最终快照校验不读CSV/MP4。

HTML使用可重复迭代器：第一遍逐条核验只保留素材导航与计数，第二遍再次校验同一冻结SHA后逐条写镜头和有界JPEG，读取结束在finally建议释放该快照/帧，异常也关闭迭代器。不在Python中保留全批报告/镜头列表；图片预算仍12MiB、单帧256KiB。缓存建议、GC和进程退出分别记录，它们都不保证腾出指定容量或避免瞬时OOM；80%工作集、95%原始占用、256MiB进程树守卫及原输入门禁保持。真实1GiB沙箱多素材与稳定性、镜头人工质量仍待验收。
