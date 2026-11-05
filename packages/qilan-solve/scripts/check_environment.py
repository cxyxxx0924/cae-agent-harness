#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
气帘计算求解技能 - 环境一键检查脚本

检查项：
  1. Python 环境（numpy, matplotlib）
  2. LS-DYNA 求解器
  3. LSPP 后处理工具（可选）
  4. HyperView（用于 d3plot → GIF 渲染）
  5. 中文字体（渲染图表）
  6. 工作目录权限

Usage:
    python check_environment.py

@author draven.chen <draven.chen@rccchina.com.cn>
@jira [main]
"""

import os
import sys
import platform
import locale
from pathlib import Path


def print_section(title):
    """打印分隔线"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def check_status(name, status, detail=""):
    """打印检查状态"""
    symbol = "✓" if status else "✗"
    status_text = "通过" if status else "失败"
    print(f"[{symbol}] {name}: {status_text}")
    if detail:
        print(f"    {detail}")
    return status


def check_python_packages():
    """检查 Python 包"""
    print_section("Python 环境")
    
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    check_status("Python 版本", sys.version_info >= (3, 10), f"版本 {py_version}")
    
    try:
        import numpy
        check_status("numpy", True, f"版本 {numpy.__version__}")
    except ImportError:
        check_status("numpy", False, "未安装 - 请运行: pip install numpy")
    
    try:
        import matplotlib
        check_status("matplotlib", True, f"版本 {matplotlib.__version__}")
    except ImportError:
        check_status("matplotlib", False, "未安装 - 请运行: pip install matplotlib")
    
    try:
        import PIL
        check_status("Pillow", True, f"版本 {PIL.__version__}")
    except ImportError:
        check_status("Pillow", False, "未安装 - 请运行: pip install Pillow")


def find_lsdyna_solver():
    """查找 LS-DYNA 求解器"""
    print_section("LS-DYNA 求解器")
    
    common_paths = [
        "D:/Program Files/ANSYS Inc/v193/ansys/bin/winx64/lsdyna_sp.exe",
        "D:/Program Files/ANSYS Inc/v193/ansys/bin/winx64/lsdyna_mpp_sp_msmpi.exe",
        "C:/Program Files/ANSYS Inc/v193/ansys/bin/winx64/lsdyna_sp.exe",
        "/opt/ansys/v193/ansys/bin/lsdyna_sp",
        "/usr/local/ansys/bin/lsdyna_sp",
    ]
    
    lsdyna_path = os.environ.get("LSDYNA_PATH")
    if lsdyna_path and os.path.isfile(lsdyna_path):
        check_status("LS-DYNA 求解器", True, f"路径: {lsdyna_path}")
        return True
    
    for path in common_paths:
        if os.path.isfile(path):
            check_status("LS-DYNA 求解器", True, f"路径: {path}")
            print(f"    提示: 可设置环境变量 LSDYNA_PATH={path}")
            return True
    
    check_status("LS-DYNA 求解器", False, 
                "未找到 - 请设置环境变量 LSDYNA_PATH 或安装到标准路径")
    return False


def find_lspp():
    """查找 LSPP 后处理工具"""
    print_section("LSPP 后处理工具（可选）")
    
    common_paths = [
        "D:/Program Files/LSTC/LS-PrePost 4.6/lsprepost4.6_x64.exe",
        "D:/Program Files/LSTC/LS-PrePost 4.7/lsprepost4.7_x64.exe",
        "C:/Program Files/LSTC/LS-PrePost 4.6/lsprepost4.6_x64.exe",
        "/usr/local/lsprepost/lsprepost",
    ]
    
    for path in common_paths:
        if os.path.isfile(path):
            check_status("LSPP", True, f"路径: {path}")
            return True
    
    check_status("LSPP", False, "未找到（非必需）")
    return False


def find_hyperview():
    """查找 HyperView 可执行文件（用于 d3plot → GIF）"""
    print_section("HyperView（用于 d3plot 渲染）")
    from render_d3plot_gif import find_hyperview as discover_hyperview
    found = discover_hyperview()
    if found:
        check_status("HyperView", True, f"路径: {found}")
        print(f"    系统编码: {locale.getpreferredencoding()}")
        return True
    check_status("HyperView", False, "未找到；请在应用设置中配置 Altair HyperWorks 版本目录")
    return False


def check_chinese_fonts():
    """检查中文字体"""
    print_section("中文字体（用于渲染）")
    
    if platform.system() != "Windows":
        check_status("中文字体", True, "非 Windows 系统，跳过检查")
        return True
    
    font_paths = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
    ]
    
    found = False
    for font in font_paths:
        if os.path.isfile(font):
            check_status("中文字体", True, f"找到: {font}")
            found = True
            break
    
    if not found:
        check_status("中文字体", False, 
                    "未找到常用中文字体 - 图表中可能显示方框")
    
    return found


def check_workspace_permissions():
    """检查工作目录权限"""
    print_section("工作目录权限")
    
    test_dir = Path.cwd() / ".env_check_test"
    try:
        test_dir.mkdir(exist_ok=True)
        test_file = test_dir / "test.txt"
        test_file.write_text("test")
        test_file.unlink()
        test_dir.rmdir()
        check_status("写入权限", True, f"工作目录: {Path.cwd()}")
        return True
    except Exception as e:
        check_status("写入权限", False, f"无法写入: {e}")
        return False


def print_summary():
    """打印使用说明"""
    print_section("环境配置完成")
    print("""
快速上手命令序列（参考 references/05_quick_setup.md）：

  # 1. K 文件门禁
  python scripts/qa_kfile_strict.py <your_deck>.k
  
  # 2. HyperView 环境检查
  python scripts/check_hyperview_setup.py
  
  # 3. 求解（MCP 或本机）
  lsdyna_sp.exe i=<your_deck>.k ncpu=4 memory=2000m
  
  # 4. 健康门禁
  python scripts/k_health_gate.py --glstat glstat --matsum matsum
  
  # 5. d3plot 渲染（需要 HyperView）
  python scripts/render_d3plot_gif.py --d3plot d3plot --output animation.gif

详细文档:
  - README.md              总览
  - references/05_quick_setup.md  快速设置清单
  - references/02_solve_setup.md  求解配置
  - references/04_postprocess_d3plot.md  后处理
""")


def main():
    """主函数"""
    print("=" * 60)
    print("  气帘计算求解技能 - 环境一键检查")
    print("=" * 60)
    
    all_checks = [
        check_python_packages(),
        find_lsdyna_solver(),
        find_lspp(),
        find_hyperview(),
        check_chinese_fonts(),
        check_workspace_permissions(),
    ]
    
    print_summary()
    
    critical_checks = [all_checks[0], all_checks[1], all_checks[3]]
    if all(critical_checks):
        print("\n✓ 关键环境检查通过！")
        return 0
    else:
        print("\n✗ 部分关键环境未配置，请参考上述提示完成配置")
        return 1


if __name__ == "__main__":
    sys.exit(main())
