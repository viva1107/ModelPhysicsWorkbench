# 第三方说明

本工具是 **Retroport Workbench** 的生物、法术、装备物理精简衍生版，原项目采用 MIT 许可证，详见 `LICENSE`。保留了原项目的 M2 物理提取、物理工具调用、文件选择器和应用启动方式。

## 运行时下载、不随包捆绑

- **Equip Plus（wxl-equip-plus）**，作者 TheDaveCalaz，GPL-3.0：
  https://github.com/TheDaveCalaz/wxl-equip-plus
  本工具仅下载并运行其 `tools/physics_table.py` 来生成 PHY2 物理表。固定提交为
  `ac7440c0db407b1dceb3573aa211cb6de68ee7c6`。本仓库及发布 ZIP 不包含该项目的源码或二进制。

## Windows 发布包

- **Python 3.14 embeddable package**，PSF-2.0：https://www.python.org
- 启动器由 Windows 自带 .NET Framework C# 编译器生成。

本工具不包含 Blizzard 的模型、贴图、声音或游戏数据；用户自行选择本地 M2／PHYS 文件。World of Warcraft 及其资源的相关权利归 Blizzard Entertainment 所有。本工具与 Blizzard Entertainment 无隶属或背书关系。
