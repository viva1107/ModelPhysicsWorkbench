Retroport 模型物理工具
======================

只从正式服 M2／PHYS 生成以下物理表：
  生物：DBFilesClient\WXLCreaturePhysics.phy2
  法术：DBFilesClient\WXLSpellPhysics.phy2
  装备：DBFilesClient\WXLEquipPlusPhysics.phy2

不包含模型转换、生物安装、装备或法术移植、坐骑、地图、DBC、SQL 或服务端功能。

启动
----
1. 完整解压 ZIP，保留 EXE 旁边的 runtime\ 和 app\。
2. 运行 Model Physics Workbench.exe。
3. 如需自定义物理工具与缓存位置，直接在“数据根目录”中填写或选择目录，无需修改源码。
4. 下载物理工具（生成时也会自动下载）。
5. 选择生物／法术／装备类型，再选择 M2／PHYS 文件或目录。
6. PFID 模型需准备对应 <FileDataID>.phys。
7. 扫描后生成。其他类型可切换后分别生成。

设置保存在 EXE 旁边的 model-physics.json，更换数据根目录后会自动保存，重启后继续有效。
未自定义数据根目录时，输出默认位于：程序目录\data\output\DBFilesClient\
自定义后默认位于：数据根目录\output\DBFilesClient\
新版不会在用户目录创建 .retroport；旧版留下的该文件夹可在确认新设置已保存后手动删除。

已有同类物理表会先备份，再与新记录增量合并：旧记录保留，新键追加，同键记录用新数据更新。
例如已有 A 后生成 B，最终表同时包含 A 和 B。请持续使用同一个输出目录。
另外两类表不受影响。本工具不会自动修改或安装到客户端。

游戏内前提：模型已能正常显示，客户端已加载支持这三类 PHY2 的 wxl-physics。
MD20 模型没有正式服物理数据；本工具不能凭空创建物理。

需要 Windows 10／11。首次下载物理工具需要访问 GitHub。
