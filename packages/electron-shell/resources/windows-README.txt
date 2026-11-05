CAE Agent - Windows x64

1. ZIP 免安装版：完整解压后双击 CAE Agent.exe。请保留 resources、
   locales 和所有 DLL 文件，不能只复制 EXE。
   EXE 安装包：运行 CAE-Agent-版本号-Windows-x64-Setup.exe，按向导
   选择安装目录；安装后从快捷方式启动。
2. 首次启动填写自己的 API Key、接口地址和模型 ID，然后保存。
   默认模型为 deepseek-flash；推理强度可在输入框下方的模型菜单中调整。
3. 需要仿真功能时，在“设置 → 仿真软件”填写本机 HyperWorks、LS-DYNA
   和仿真工作目录。HyperWorks、LS-DYNA 需要自行安装并配置许可证。

适用系统：Windows 10/11 64 位。
已包含 Node.js 24.14.0、uv 和聊天后台依赖，无需安装 Node.js 或 pnpm。
首次启用 Python 仿真工具时需要联网；uv 会下载所需的 Python 环境和依赖。
本包没有包含个人 API Key。设置保存在当前 Windows 用户的数据目录中。
