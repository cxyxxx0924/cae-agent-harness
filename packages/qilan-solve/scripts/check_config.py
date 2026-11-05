#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置检查脚本

验证 LS-DYNA 求解器配置是否正确

@author draven.chen <draven.chen@rccchina.com.cn>
@jira [feature/integrate-qilian-solve-skill]
"""

import os
import sys
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR.parent / "config" / "solver.json"


def check_file(path, name):
    """检查文件是否存在"""
    p = Path(path)
    if p.exists():
        print(f"  ✓ {name}: {path}")
        return True
    else:
        print(f"  ✗ {name} NOT FOUND: {path}")
        return False


def check_dir(path, name):
    """检查目录是否存在"""
    p = Path(path)
    if p.exists() and p.is_dir():
        print(f"  ✓ {name}: {path}")
        return True
    else:
        print(f"  ✗ {name} NOT FOUND: {path}")
        return False


def main():
    print("\n" + "="*70)
    print("LS-DYNA 求解器配置检查")
    print("="*70)
    
    # 检查配置文件
    print("\n[1] 配置文件")
    if not CONFIG_PATH.exists():
        print(f"  ✗ 配置文件不存在: {CONFIG_PATH}")
        return 1
    
    print(f"  ✓ 配置文件: {CONFIG_PATH}")
    
    # 加载配置
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    all_ok = True
    
    # 检查求解器
    print("\n[2] LS-DYNA 求解器")
    solver_exe = config['solver']['executable']
    if not check_file(solver_exe, "Solver executable"):
        all_ok = False
        print("     提示：检查 ANSYS 安装路径")
    
    # 检查许可
    print("\n[3] 许可配置")
    license_file = config['license']['env']['ANSYSLMD_LICENSE_FILE']
    if not check_file(license_file, "License file"):
        all_ok = False
        print("     提示：检查 ANSYS 许可文件路径")
    
    ansyscl_path = config['license']['ansyscl_path']
    if not check_file(ansyscl_path, "ansyscl.exe"):
        all_ok = False
        print("     提示：检查 ANSYS Shared Files 路径")
    
    # 检查工作空间
    print("\n[4] 工作空间")
    workspaces = config['workspaces']
    
    # 注意：Windows 路径在 macOS 上无法验证，这里只做提示
    print("  注意：以下为 Windows 路径，在当前系统上无法验证")
    for key, path in workspaces.items():
        print(f"  - {key}: {path}")
    
    # 检查默认模型
    print("\n[5] 默认车身模型")
    default_vehicle = config.get('default_models', {}).get('vehicle')
    if default_vehicle:
        default_path = SCRIPT_DIR.parent / default_vehicle
        if not check_file(default_path, "Default vehicle model"):
            all_ok = False
    else:
        print("  ✗ 未配置默认车身模型")
    
    # 检查 Python 依赖
    print("\n[6] Python 依赖")
    required_modules = ['numpy', 'matplotlib', 'pandas']
    
    for module in required_modules:
        try:
            __import__(module)
            print(f"  ✓ {module}")
        except ImportError:
            print(f"  ✗ {module} NOT INSTALLED")
            all_ok = False
    
    if not all_ok:
        print("\n提示：运行 pip install numpy matplotlib pandas")
    
    # 总结
    print("\n" + "="*70)
    if all_ok:
        print("配置检查通过 ✓")
        print("\n可以开始运行任务：")
        print("  python scripts/solve_workflow.py task1")
        print("  python scripts/solve_workflow.py task2")
        print("  python scripts/solve_workflow.py task3")
    else:
        print("配置检查失败 ✗")
        print("\n请修复上述问题后重试")
        print("参考文档：CONFIGURE.md")
    print("="*70)
    
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
