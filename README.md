# Retroport 模型物理工具

这是 Retroport Workbench 的**物理专用精简版**，支持生物、法术和装备三类物理表：

| 类型 | 输出文件 |
|---|---|
| 生物 | `DBFilesClient\WXLCreaturePhysics.phy2` |
| 法术 | `DBFilesClient\WXLSpellPhysics.phy2` |
| 装备 | `DBFilesClient\WXLEquipPlusPhysics.phy2` |

不包含装备移植、生物安装、坐骑、法术移植、地图、模型转换、3D 预览、DBC／SQL 生成或服务端操作。

## 使用

1. 运行 `Model Physics Workbench.exe`；源码运行则执行 `Workbench.bat`。
2. 点击“下载物理工具”。生成时如果尚未下载，也会自动下载。
3. 选择本次类型：**生物、法术或装备**。
4. 选择一个 `.m2`／`.phys` 文件，或选择包含这些文件的目录。
5. 如果 M2 使用 PFID 引用外部物理，请设置包含对应 `<FileDataID>.phys` 的目录。程序也会检查模型所在目录。
6. 点击“扫描物理数据”，确认哪些文件可生成。
7. 点击生成按钮。需要其他类型时，切换类型后分别生成。

输出到所选目录的 `DBFilesClient` 子目录。每批生成一种表，不会覆盖另外两类文件；已有同类文件会先备份为 `.bak-日期时间`，再写入新表。

生成时会自动读取输出目录中的同名 PHY2 并进行**增量合并**：已有 A 时再生成 B，结果会同时保留 A 和 B；完全相同的模型键使用本次新数据更新，其余旧记录原样保留。请持续使用同一个输出目录。若需要完全重建一张表，请先移走旧 PHY2；若当前表已只剩 B，可先把包含 A 的旧表或备份恢复为该 PHY2，再生成 B。

### 客户端路径键

PHY2 需要按客户端报告的模型路径索引。选择目录时，工具使用相对于该目录的路径；选择单个文件时使用文件名。每条记录还会加入不带目录的文件名作为别名。

如果客户端模型路径需要额外前缀，可填写例如 `creature\custom`。扫描结果会显示实际写入的键。

## 重要限制

- 支持带 PFDC／PFID 的正式服 MD21 模型，以及独立 `.phys` 文件。
- WotLK MD20 模型没有正式服物理数据，会显示“无物理”。
- 模型必须已经能在 3.3.5a 客户端正常显示；本工具不负责模型转换。
- 游戏内需要加载支持这三类 PHY2 的 `wxl-physics` 客户端扩展。
- 输出文件仍需按你的客户端补丁方式打包或放置，本工具不会自动安装到游戏。
- 装备物理表不负责装备转换，法术物理表不负责法术移植。

## 自定义数据根目录

编译后可直接在界面的“数据根目录”中输入路径或点击“选目录”，例如 `D:\ModelPhysics`。设置会持久保存，无需修改源码。物理工具、缓存和默认输出会使用新目录；已经单独设置的自定义输出目录不受影响。

更改目录后可重新下载工具，或把原目录下的 `deps` 复制过去。设置会自动保存到 EXE 旁边的 `model-physics.json`，重启后继续有效；点击“下载物理工具”也会先保存当前界面的路径，避免保存与下载同时发生时使用旧目录。

新版采用便携配置，不会在 `%USERPROFILE%` 下创建 `.retroport`。首次启动时会尝试迁移旧版设置；旧版已经生成的 `.retroport` 文件夹不会自动删除，确认新设置已保存后可手动清理。

未自定义时，默认数据目录和工具位置为：

```text
程序目录\data\
程序目录\data\deps\equip-plus\tools\physics_table.py
```

## GitHub Actions 构建

仓库已带 `.github/workflows/release.yml`：

1. 打开 **Actions → release → Run workflow**。
2. 等待测试和 Windows 构建完成。
3. 在 **Artifacts** 下载 `Model-Physics-Workbench`。

推送 `v0.3.0` 等 `v*` 标签时，也会把 ZIP 附加到对应 Release。

## Windows 本地构建

```bat
python -m pip install -e ".[dev]"
python -m pytest -q tests
python packaging/build_release.py --out dist
```

产物：

```text
dist\Model-Physics-Workbench-0.3.0-win64.zip
```

发布包包含 EXE 启动器、随包 Python 运行环境和应用代码。EXE 不是单个原生物理引擎程序，物理表仍由外部 `physics_table.py` 生成。
