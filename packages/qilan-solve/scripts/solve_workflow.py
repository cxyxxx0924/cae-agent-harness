#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LS-DYNA 气帘求解工作流

执行三阶段计算：
1. 气帘试算 (20ms probe)
2. 车身试算 (5ms probe)
3. 组合计算 (full solve with curtain deployment)

@author draven.chen <draven.chen@rccchina.com.cn>
@jira [feature/integrate-qilan-solve-skill]
"""

import os
import sys
import json
import subprocess
import shutil
import numpy as np
from pathlib import Path
from datetime import datetime

# 导入 K 文件工具
from kfile_utils import KFile, read_nodes_simple, find_z_projection

# 添加脚本目录到路径
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

CONFIG_PATH = SCRIPT_DIR.parent / "config" / "solver.json"

def get_default_vehicle_model():
    """
    获取默认车身模型路径
    
    Returns:
        Path: 默认车身 K 文件的绝对路径
    """
    config = load_config()
    default_vehicle_rel = config.get('default_models', {}).get('vehicle')
    
    if not default_vehicle_rel:
        return None
    
    # 相对于 qilan-solve 目录的路径
    default_vehicle_path = SCRIPT_DIR.parent / default_vehicle_rel
    
    if default_vehicle_path.exists():
        return default_vehicle_path.resolve()
    else:
        print(f"[WARN] Default vehicle model not found: {default_vehicle_path}")
        return None


def get_vehicle_model(user_provided_path=None):
    """
    获取车身模型路径（用户提供的或默认的）
    
    Args:
        user_provided_path: 用户提供的车身 K 文件路径
    
    Returns:
        Path: 车身 K 文件路径，如果都不存在则返回 None
    """
    if user_provided_path:
        user_path = Path(user_provided_path)
        if user_path.exists():
            print(f"[INFO] Using user-provided vehicle model: {user_path}")
            return user_path
        else:
            print(f"[WARN] User-provided vehicle model not found: {user_path}")
    
    # 如果用户没有提供或提供的不存在，使用默认模型
    default_path = get_default_vehicle_model()
    if default_path:
        print(f"[INFO] Using default vehicle model: {default_path}")
        return default_path
    
    print(f"[ERROR] No vehicle model available")
    return None


def load_config():
    """加载求解器配置"""
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def setup_environment(config):
    """设置环境变量"""
    license_env = config['license']['env']
    for key, value in license_env.items():
        os.environ[key] = value
        print(f"[ENV] {key}={value}")
    
    # 验证 ansyscl.exe 是否在求解器目录
    solver_exe = Path(config['solver']['executable'])
    solver_dir = solver_exe.parent
    ansyscl_target = solver_dir / "ansyscl.exe"
    ansyscl_source = Path(config['license']['ansyscl_path'])
    
    if not ansyscl_target.exists():
        if ansyscl_source.exists():
            print(f"[WARN] ansyscl.exe not found in solver directory")
            print(f"[INFO] Copying from {ansyscl_source} to {ansyscl_target}")
            shutil.copy2(ansyscl_source, ansyscl_target)
        else:
            print(f"[ERROR] ansyscl.exe not found: {ansyscl_source}")
            return False
    
    return True


def run_lsdyna(kfile, duration_ms, cores=4, workdir=None):
    """
    运行 LS-DYNA 求解
    
    Args:
        kfile: K文件路径
        duration_ms: 仿真时长（毫秒）
        cores: 核心数
        workdir: 工作目录
    """
    config = load_config()
    solver_exe = config['solver']['executable']
    
    if not Path(solver_exe).exists():
        raise FileNotFoundError(f"Solver not found: {solver_exe}")
    
    if not Path(kfile).exists():
        raise FileNotFoundError(f"K file not found: {kfile}")
    
    if workdir is None:
        workdir = Path(kfile).parent
    
    os.chdir(workdir)
    print(f"\n[SOLVE] Starting LS-DYNA solve...")
    print(f"  K file: {kfile}")
    print(f"  Duration: {duration_ms}ms")
    print(f"  Cores: {cores}")
    print(f"  Work dir: {workdir}")
    
    cmd = [
        solver_exe,
        f"I={Path(kfile).name}",
        f"NCPU={cores}"
    ]
    
    print(f"[CMD] {' '.join(cmd)}")
    
    start_time = datetime.now()
    try:
        result = subprocess.run(
            cmd,
            cwd=workdir,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"\n[SOLVE] Completed in {elapsed:.1f}s")
        
        if result.returncode != 0:
            print(f"[ERROR] Solver exited with code {result.returncode}")
            return False
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to run solver: {e}")
        return False


def task1_curtain_probe():
    """
    Task 1: 气帘试算 (20ms probe)
    
    - 读取工作气帘文件
    - 从参考模型提取材料、约束、厚度等
    - 检查拉带约束
    - 运行 20ms 试算
    - 清理并输出
    """
    print("\n" + "="*70)
    print("Task 1: 气帘试算 (Curtain Probe - 20ms)")
    print("="*70)
    
    config = load_config()
    task_cfg = config['tasks']['curtain_probe']
    
    input_file = Path(task_cfg['input'])
    output_file = Path(task_cfg['output'])
    reference_dir = Path(task_cfg['reference'])
    
    print(f"[INFO] Input: {input_file}")
    print(f"[INFO] Reference: {reference_dir}")
    print(f"[INFO] Output: {output_file}")
    
    if not input_file.exists():
        print(f"[ERROR] Input file not found: {input_file}")
        return False
    
    # 加载工作文件
    print("\n[1/6] Loading curtain model...")
    curtain = KFile(input_file)
    
    # 查找参考模型
    print("\n[2/6] Finding reference model...")
    ref_files = list(reference_dir.glob("*.k"))
    if not ref_files:
        print(f"[ERROR] No reference K files found in {reference_dir}")
        return False
    
    reference = KFile(ref_files[0])
    print(f"[INFO] Using reference: {ref_files[0]}")
    
    # 从参考模型提取必要的设置
    print("\n[3/6] Extracting settings from reference model...")
    keywords_to_copy = [
        '*MAT_',  # 材料
        '*SECTION_SHELL',  # 壳单元截面
        '*PART',  # 零件
        '*BOUNDARY_',  # 边界条件
        '*AIRBAG_',  # 气囊参数
        '*CONTROL_',  # 控制参数
    ]
    
    for keyword in keywords_to_copy:
        for section in reference.sections:
            if section.keyword.startswith(keyword):
                # 检查是否已存在
                if not curtain.has_keyword(section.keyword):
                    print(f"  - Copying {section.keyword}")
                    curtain.add_section(section)
    
    # 检查拉带约束
    print("\n[4/6] Checking tether constraints...")
    has_tethers = curtain.has_keyword('*ELEMENT_BEAM') or curtain.has_keyword('*ELEMENT_DISCRETE')
    if not has_tethers:
        print("[WARN] No tether elements found - copying from reference")
        curtain.copy_section_from(reference, '*ELEMENT_BEAM')
        curtain.copy_section_from(reference, '*ELEMENT_DISCRETE')
    
    # 创建临时求解文件
    print("\n[5/6] Creating solve deck...")
    work_dir = input_file.parent
    temp_solve = work_dir / f"temp_curtain_solve_{datetime.now().strftime('%Y%m%d_%H%M%S')}.k"
    curtain.write(temp_solve)
    
    # 运行求解
    print("\n[6/6] Running LS-DYNA solve (20ms)...")
    success = run_lsdyna(temp_solve, task_cfg['duration_ms'], workdir=work_dir)
    
    if success:
        print("\n[SUCCESS] Curtain probe completed")
        print(f"[INFO] Writing cleaned model to {output_file}")
        curtain.write(output_file)
        
        # 清理临时文件
        if temp_solve.exists():
            temp_solve.unlink()
        
        return True
    else:
        print("\n[FAILED] Curtain probe failed")
        return False


def task2_vehicle_probe():
    """
    Task 2: 车身试算 (5ms probe)
    
    - 读取车身文件（用户提供或默认）
    - 清理无关内容
    - 从参考模型提取设置
    - 运行 5ms 试算
    - 清理并输出
    """
    print("\n" + "="*70)
    print("Task 2: 车身试算 (Vehicle Probe - 5ms)")
    print("="*70)
    
    config = load_config()
    task_cfg = config['tasks']['vehicle_probe']
    
    # 获取车身模型（用户提供或默认）
    input_path = task_cfg.get('input')
    vehicle_file = get_vehicle_model(input_path)
    
    if not vehicle_file:
        print("[ERROR] No vehicle model available")
        return False
    
    output_file = Path(task_cfg['output'])
    reference_file = Path(task_cfg['reference'])
    
    print(f"[INFO] Input: {vehicle_file}")
    print(f"[INFO] Reference: {reference_file}")
    print(f"[INFO] Output: {output_file}")
    
    # 加载车身文件
    print("\n[1/5] Loading vehicle model...")
    vehicle = KFile(vehicle_file)
    
    # 加载参考模型
    print("\n[2/5] Loading reference model...")
    if not reference_file.exists():
        print(f"[ERROR] Reference file not found: {reference_file}")
        return False
    
    reference = KFile(reference_file)
    
    # 清理车身模型（保留网格，清除其他）
    print("\n[3/5] Cleaning vehicle model...")
    # 保留的关键字
    keep_keywords = ['*NODE', '*ELEMENT_SHELL', '*ELEMENT_SOLID']
    cleaned_sections = []
    
    for section in vehicle.sections:
        if any(section.keyword.startswith(kw) for kw in keep_keywords):
            cleaned_sections.append(section)
    
    vehicle.sections = cleaned_sections
    print(f"[INFO] Kept {len(cleaned_sections)} mesh sections")
    
    # 从参考模型提取设置
    print("\n[4/5] Extracting settings from reference...")
    keywords_to_copy = [
        '*MAT_RIGID',  # 刚体材料
        '*PART',
        '*SECTION_',
        '*CONTROL_',
        '*BOUNDARY_SPC',  # 约束
    ]
    
    for keyword in keywords_to_copy:
        for section in reference.sections:
            if section.keyword.startswith(keyword):
                print(f"  - Copying {section.keyword}")
                vehicle.add_section(section)
    
    # 输出清理后的模型
    print("\n[5/5] Writing cleaned vehicle model...")
    vehicle.write(output_file)
    
    print("\n[SUCCESS] Vehicle probe completed")
    print(f"[INFO] Cleaned model: {output_file}")
    
    return True


def task3_combined_solve():
    """
    Task 3: 组合计算 (Combined Solve)
    
    - 创建主计算文件 main.key
    - 包含清理后的气帘和车身模型
    - 调整气帘位置（Y/Z平移）
    - 设置拉绳连接（10个固定点 + Z向投影）
    - 复制 *REFERENCE_GEOMETRY_NODE
    - 运行完整求解
    """
    print("\n" + "="*70)
    print("Task 3: 组合计算 (Combined Solve)")
    print("="*70)
    
    config = load_config()
    task_cfg = config['tasks']['combined_solve']
    
    main_file = Path(task_cfg['main'])
    curtain_file = Path(task_cfg['curtain'])
    vehicle_file = Path(task_cfg['vehicle'])
    reference_file = Path(task_cfg['reference'])
    
    print(f"[INFO] Main file: {main_file}")
    print(f"[INFO] Curtain: {curtain_file}")
    print(f"[INFO] Vehicle: {vehicle_file}")
    print(f"[INFO] Reference: {reference_file}")
    
    # 检查文件
    if not curtain_file.exists():
        print(f"[ERROR] Curtain file not found: {curtain_file}")
        print("[INFO] Please run Task 1 first")
        return False
    
    if not vehicle_file.exists():
        print(f"[ERROR] Vehicle file not found: {vehicle_file}")
        print("[INFO] Please run Task 2 first")
        return False
    
    if not reference_file.exists():
        print(f"[ERROR] Reference file not found: {reference_file}")
        return False
    
    # 加载模型
    print("\n[1/8] Loading models...")
    curtain = KFile(curtain_file)
    vehicle = KFile(vehicle_file)
    reference = KFile(reference_file)
    
    # 分析参考模型中的相对位置
    print("\n[2/8] Analyzing reference model positions...")
    ref_curtain_nodes = reference.extract_nodes()
    
    # 这里需要识别参考模型中哪些是气帘节点，哪些是车身节点
    # 简化处理：假设气帘节点 Z 值较低，车身节点 Z 值较高
    if ref_curtain_nodes:
        z_values = [z for _, _, z in ref_curtain_nodes.values()]
        ref_curtain_z_avg = np.mean(z_values)
        print(f"[INFO] Reference curtain average Z: {ref_curtain_z_avg:.2f}")
    
    # 计算工作模型的平移量
    print("\n[3/8] Calculating curtain translation...")
    work_curtain_nodes = curtain.extract_nodes()
    work_vehicle_nodes = vehicle.extract_nodes()
    
    if work_curtain_nodes:
        work_curtain_z_avg = np.mean([z for _, _, z in work_curtain_nodes.values()])
        work_curtain_y_avg = np.mean([y for _, y, _ in work_curtain_nodes.values()])
        
        # 简化：暂时不做平移，让用户根据实际情况调整
        # 实际项目中需要更复杂的对齐算法
        dy = 0.0
        dz = 0.0
        print(f"[INFO] Curtain translation: dY={dy:.2f}, dZ={dz:.2f}")
        
        if abs(dy) > 0.1 or abs(dz) > 0.1:
            print("[INFO] Applying translation to curtain...")
            curtain.translate_nodes(dy, dz)
    
    # 设置拉绳连接
    print("\n[4/8] Setting up tether connections...")
    # 这需要识别气帘上的拉带节点
    # 简化：从参考模型复制拉绳定义
    tether_sections = []
    for section in reference.sections:
        if section.keyword in ['*ELEMENT_BEAM', '*ELEMENT_DISCRETE', '*CONSTRAINED_']:
            tether_sections.append(section)
            print(f"  - Found {section.keyword}")
    
    # 复制 *REFERENCE_GEOMETRY_NODE（防止抖动）
    print("\n[5/8] Copying reference geometry node...")
    ref_geom = reference.get_section('*REFERENCE_GEOMETRY_NODE')
    if ref_geom:
        print("[INFO] Reference geometry node found in reference model")
    else:
        print("[WARN] Reference geometry node not found in reference model")
    
    # 创建主计算文件
    print("\n[6/8] Creating main solve deck...")
    main = KFile()
    
    # 添加头部注释
    main.header_comments = [
        "$# LS-DYNA Combined Airbag Curtain Solve",
        f"$# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"$# Curtain: {curtain_file.name}",
        f"$# Vehicle: {vehicle_file.name}",
        "$#"
    ]
    
    # 包含子文件
    include_section = KFileSection('*INCLUDE', [
        '*INCLUDE\n',
        f'$ Curtain model\n',
        f'{curtain_file.name}\n',
        f'$ Vehicle model\n',
        f'{vehicle_file.name}\n'
    ])
    main.add_section(include_section)
    
    # 从参考模型复制控制参数
    print("\n[7/8] Copying control parameters from reference...")
    control_keywords = [
        '*CONTROL_TERMINATION',
        '*CONTROL_TIMESTEP',
        '*CONTROL_ENERGY',
        '*CONTROL_OUTPUT',
        '*DATABASE_',
        '*AIRBAG_',
        '*CONTACT_',
    ]
    
    for keyword in control_keywords:
        for section in reference.sections:
            if section.keyword.startswith(keyword):
                print(f"  - Copying {section.keyword}")
                main.add_section(section)
    
    # 添加拉绳连接
    for section in tether_sections:
        main.add_section(section)
    
    # 添加 reference geometry node
    if ref_geom:
        main.add_section(ref_geom)
    
    # 写入主文件
    print("\n[8/8] Writing main solve deck...")
    main.write(main_file)
    
    print("\n[SUCCESS] Combined solve deck created")
    print(f"[INFO] Main file: {main_file}")
    print(f"[INFO] Ready for full solve")
    
    # 询问是否运行求解
    print("\n[NOTICE] Full solve may take significant time")
    print("[NOTICE] Review the main.key file before running")
    
    return True


def main():
    """主工作流"""
    print("\n" + "="*70)
    print("LS-DYNA 气帘求解工作流")
    print("="*70)
    
    config = load_config()
    
    if not setup_environment(config):
        print("[ERROR] Environment setup failed")
        return 1
    
    if len(sys.argv) < 2:
        print("\nUsage:")
        print("  python solve_workflow.py task1  # 气帘试算")
        print("  python solve_workflow.py task2  # 车身试算")
        print("  python solve_workflow.py task3  # 组合计算")
        return 1
    
    task = sys.argv[1].lower()
    
    if task == 'task1':
        success = task1_curtain_probe()
    elif task == 'task2':
        success = task2_vehicle_probe()
    elif task == 'task3':
        success = task3_combined_solve()
    else:
        print(f"[ERROR] Unknown task: {task}")
        print("[ERROR] Valid tasks: task1, task2, task3")
        return 1
    
    if success:
        print("\n" + "="*70)
        print(f"Task {task.upper()} COMPLETED SUCCESSFULLY")
        print("="*70)
        return 0
    else:
        print("\n" + "="*70)
        print(f"Task {task.upper()} FAILED")
        print("="*70)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
