CAE Agent - Windows x64

1. ZIP 免安装版：完整解压后双击 CAE Agent.exe。请保留 resources、
   locales 和所有 DLL 文件，不能只复制 EXE。
   EXE 安装包：运行 CAE-Agent-版本号-Windows-x64-Setup.exe，按向导
   选择安装目录；安装后从快捷方式启动。
2. 首次启动填写自己的 API Key、接口地址和模型 ID，然后保存。
   可获取接口模型列表或手动添加模型；以后通过“设置 → 模型”修改。
   默认模型不可用时，可在输入框下方的模型菜单中切换其他已保存模型。
   DeepSeek Flash / V4 Pro 的推理强度也可在该菜单中调整。
3. 在“设置 → 仿真软件”选择求解位置：本地或服务端。本地可继续选择
   “软件”（填写 LS-DYNA 路径）或“求解服务”（填写本机服务地址）。
   服务端模式填写远程服务地址；两种服务模式均支持可选的访问令牌和测试连接。
   求解服务需另行部署并支持 CAE Agent 的 /health、/solve HTTP 接口；
   模型及引用文件需能被服务访问，客户端不会自动上传模型或下载结果。
4. 本机前后处理按需配置 HyperWorks 和仿真工作目录；本地软件求解需
   自行安装 LS-DYNA。运行这些仿真软件均需配置对应许可证。

适用系统：Windows 10/11 64 位。
已包含 Node.js 24.14.0、uv 和聊天后台依赖，无需安装 Node.js 或 pnpm。
首次启用 Python 仿真工具时需要联网；应用会在聊天界面启动后由 uv 在后台下载所需的 Python 环境和依赖，打包版默认使用清华 PyPI 镜像。下载完成后工具会自动上线，网络失败会自动重试；可通过 UV_INDEX_URL 或 CAE_UV_INDEX_URL 指定其他镜像。
本包没有包含个人 API Key。设置保存在当前 Windows 用户的数据目录中。

启动排查：
应用仅运行一个实例，重复打开会显示现有窗口。后台端口被占用时会直接提示。
启动日志：%APPDATA%\@cae\electron-shell\logs\startup.log
启动失败窗口会显示日志路径和最近的后台输出。日志会遮盖已配置的密钥和启动 token。
