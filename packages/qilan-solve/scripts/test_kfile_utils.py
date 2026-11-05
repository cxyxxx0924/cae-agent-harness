#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
K 文件工具测试脚本

测试 kfile_utils.py 的基本功能

@author draven.chen <draven.chen@rccchina.com.cn>
@jira [feature/integrate-qilian-solve-skill]
"""

import sys
from pathlib import Path

# 添加脚本目录到路径
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from kfile_utils import KFile, read_nodes_simple, find_z_projection


def test_default_vehicle():
    """测试读取默认车身模型"""
    print("\n" + "="*70)
    print("测试：读取默认车身模型")
    print("="*70)
    
    default_vehicle = SCRIPT_DIR.parent / "resources" / "default-models" / "BIW_default.k"
    
    if not default_vehicle.exists():
        print(f"✗ 默认车身模型不存在: {default_vehicle}")
        return False
    
    print(f"✓ 找到默认车身模型: {default_vehicle}")
    
    # 测试加载
    print("\n读取节点...")
    nodes = read_nodes_simple(default_vehicle)
    
    if nodes:
        print(f"✓ 成功读取 {len(nodes)} 个节点")
        
        # 显示一些统计信息
        x_coords = [x for x, y, z in nodes.values()]
        y_coords = [y for x, y, z in nodes.values()]
        z_coords = [z for x, y, z in nodes.values()]
        
        print(f"\n节点范围:")
        print(f"  X: [{min(x_coords):.2f}, {max(x_coords):.2f}]")
        print(f"  Y: [{min(y_coords):.2f}, {max(y_coords):.2f}]")
        print(f"  Z: [{min(z_coords):.2f}, {max(z_coords):.2f}]")
        
        return True
    else:
        print("✗ 未能读取节点")
        return False


def test_kfile_class():
    """测试 KFile 类"""
    print("\n" + "="*70)
    print("测试：KFile 类功能")
    print("="*70)
    
    default_vehicle = SCRIPT_DIR.parent / "resources" / "default-models" / "BIW_default.k"
    
    if not default_vehicle.exists():
        print(f"✗ 默认车身模型不存在: {default_vehicle}")
        return False
    
    print("加载 K 文件...")
    kfile = KFile(default_vehicle)
    
    print(f"✓ 成功加载 K 文件")
    print(f"  - 找到 {len(kfile.sections)} 个段")
    print(f"  - 头部注释行数: {len(kfile.header_comments)}")
    
    # 列出所有关键字
    keywords = set(s.keyword for s in kfile.sections)
    print(f"\n找到的关键字 ({len(keywords)}):")
    for kw in sorted(keywords):
        count = len([s for s in kfile.sections if s.keyword == kw])
        print(f"  - {kw}: {count} 次")
    
    # 测试提取节点
    print("\n提取节点...")
    nodes = kfile.extract_nodes()
    print(f"✓ 提取了 {len(nodes)} 个节点")
    
    return True


def test_z_projection():
    """测试 Z 向投影功能"""
    print("\n" + "="*70)
    print("测试：Z 向投影算法")
    print("="*70)
    
    # 创建测试数据
    curtain_node = (100.0, 200.0, 50.0)  # 气帘节点（较低）
    
    vehicle_nodes = {
        1: (100.0, 200.0, 150.0),  # 正上方
        2: (105.0, 205.0, 140.0),  # 附近但稍低
        3: (110.0, 210.0, 160.0),  # 较远但更高
        4: (100.0, 200.0, 30.0),   # 下方（应被忽略）
    }
    
    print(f"气帘节点: {curtain_node}")
    print(f"车身节点: {len(vehicle_nodes)} 个")
    
    result = find_z_projection(curtain_node, vehicle_nodes, search_radius=50.0)
    
    if result:
        print(f"✓ 找到投影节点: {result}")
        print(f"  位置: {vehicle_nodes[result]}")
        
        # 验证结果
        if result == 1:
            print("✓ 算法正确：选择了正上方最近的节点")
            return True
        else:
            print("✗ 算法可能有问题：没有选择最优节点")
            return False
    else:
        print("✗ 未找到投影节点")
        return False


def main():
    print("\n" + "="*70)
    print("K 文件工具测试套件")
    print("="*70)
    
    tests = [
        ("默认车身模型读取", test_default_vehicle),
        ("KFile 类功能", test_kfile_class),
        ("Z 向投影算法", test_z_projection),
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n✗ 测试异常: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # 总结
    print("\n" + "="*70)
    print("测试总结")
    print("="*70)
    
    for name, success in results:
        status = "✓" if success else "✗"
        print(f"{status} {name}")
    
    passed = sum(1 for _, s in results if s)
    total = len(results)
    
    print(f"\n通过: {passed}/{total}")
    
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
