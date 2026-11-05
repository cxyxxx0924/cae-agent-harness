#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LS-DYNA K 文件操作工具库

提供 K 文件的读取、解析、修改、合并等功能

@author draven.chen <draven.chen@rccchina.com.cn>
@jira [feature/integrate-qilian-solve-skill]
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class KFileSection:
    """K 文件的一个关键字段"""
    def __init__(self, keyword: str, lines: List[str]):
        self.keyword = keyword
        self.lines = lines
    
    def __repr__(self):
        return f"KFileSection({self.keyword}, {len(self.lines)} lines)"


class KFile:
    """LS-DYNA K 文件对象"""
    
    def __init__(self, path: Optional[Path] = None):
        self.path = path
        self.sections: List[KFileSection] = []
        self.header_comments: List[str] = []
        
        if path and path.exists():
            self.load(path)
    
    def load(self, path: Path):
        """加载 K 文件"""
        self.path = Path(path)
        
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        self._parse(content)
    
    def _parse(self, content: str):
        """解析 K 文件内容"""
        lines = content.split('\n')
        
        current_keyword = None
        current_lines = []
        in_header = True
        
        for line in lines:
            stripped = line.strip().upper()
            
            # 处理头部注释
            if in_header and (not stripped or stripped.startswith('$')):
                self.header_comments.append(line)
                continue
            
            # 关键字行
            if stripped.startswith('*'):
                # 保存上一个段
                if current_keyword:
                    self.sections.append(KFileSection(current_keyword, current_lines))
                
                in_header = False
                current_keyword = stripped.split()[0] if stripped.split() else stripped
                current_lines = [line]
            
            # 数据行
            elif current_keyword:
                current_lines.append(line)
        
        # 保存最后一个段
        if current_keyword:
            self.sections.append(KFileSection(current_keyword, current_lines))
    
    def get_section(self, keyword: str) -> Optional[KFileSection]:
        """获取指定关键字的第一个段"""
        keyword_upper = keyword.upper()
        for section in self.sections:
            if section.keyword == keyword_upper:
                return section
        return None
    
    def get_all_sections(self, keyword: str) -> List[KFileSection]:
        """获取指定关键字的所有段"""
        keyword_upper = keyword.upper()
        return [s for s in self.sections if s.keyword == keyword_upper]
    
    def has_keyword(self, keyword: str) -> bool:
        """检查是否包含指定关键字"""
        return self.get_section(keyword) is not None
    
    def remove_section(self, keyword: str):
        """删除指定关键字的所有段"""
        keyword_upper = keyword.upper()
        self.sections = [s for s in self.sections if s.keyword != keyword_upper]
    
    def add_section(self, section: KFileSection):
        """添加一个段"""
        self.sections.append(section)
    
    def copy_section_from(self, other: 'KFile', keyword: str):
        """从另一个 K 文件复制指定关键字的所有段"""
        sections = other.get_all_sections(keyword)
        for section in sections:
            self.add_section(section)
    
    def extract_nodes(self) -> Dict[int, Tuple[float, float, float]]:
        """提取所有节点：{nid: (x, y, z)}"""
        nodes = {}
        
        for section in self.get_all_sections('*NODE'):
            for line in section.lines[1:]:  # 跳过关键字行
                line = line.strip()
                if not line or line.startswith('$'):
                    continue
                
                # 支持逗号分隔和空格分隔
                parts = line.replace(',', ' ').split()
                if len(parts) >= 4:
                    try:
                        nid = int(float(parts[0]))
                        x = float(parts[1])
                        y = float(parts[2])
                        z = float(parts[3])
                        nodes[nid] = (x, y, z)
                    except ValueError:
                        continue
        
        return nodes
    
    def translate_nodes(self, dy: float = 0.0, dz: float = 0.0):
        """平移所有节点"""
        for section in self.get_all_sections('*NODE'):
            new_lines = [section.lines[0]]  # 保留关键字行
            
            for line in section.lines[1:]:
                stripped = line.strip()
                if not stripped or stripped.startswith('$'):
                    new_lines.append(line)
                    continue
                
                # 解析节点
                parts = line.replace(',', ' ').split()
                if len(parts) >= 4:
                    try:
                        nid = int(float(parts[0]))
                        x = float(parts[1])
                        y = float(parts[2]) + dy
                        z = float(parts[3]) + dz
                        
                        # 重新格式化
                        new_line = f"{nid:>8}{x:>16.8f}{y:>16.8f}{z:>16.8f}\n"
                        new_lines.append(new_line)
                    except ValueError:
                        new_lines.append(line)
                else:
                    new_lines.append(line)
            
            section.lines = new_lines
    
    def write(self, output_path: Path):
        """写入 K 文件"""
        with open(output_path, 'w', encoding='utf-8') as f:
            # 写入头部注释
            for comment in self.header_comments:
                f.write(comment + '\n')
            
            # 写入所有段
            for section in self.sections:
                for line in section.lines:
                    f.write(line if line.endswith('\n') else line + '\n')
                f.write('\n')  # 段之间空行
            
            # 写入结束标记
            f.write('*END\n')


def read_nodes_simple(kfile_path: Path) -> Dict[int, Tuple[float, float, float]]:
    """简单读取节点坐标（不解析整个文件）"""
    nodes = {}
    in_node_section = False
    
    with open(kfile_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            upper = line.strip().upper()
            
            if upper.startswith('*'):
                in_node_section = upper.startswith('*NODE') and 'REFERENCE' not in upper
                continue
            
            if not in_node_section or not line.strip() or line.strip().startswith('$'):
                continue
            
            parts = line.replace(',', ' ').split()
            if len(parts) >= 4:
                try:
                    nid = int(float(parts[0]))
                    x = float(parts[1])
                    y = float(parts[2])
                    z = float(parts[3])
                    nodes[nid] = (x, y, z)
                except ValueError:
                    continue
    
    return nodes


def find_z_projection(curtain_node: Tuple[float, float, float],
                      vehicle_nodes: Dict[int, Tuple[float, float, float]],
                      search_radius: float = 100.0) -> Optional[int]:
    """
    从气帘节点向上（Z方向）投影，找到车身上的对应节点
    
    Args:
        curtain_node: 气帘节点坐标 (x, y, z)
        vehicle_nodes: 车身所有节点 {nid: (x, y, z)}
        search_radius: XY平面搜索半径（mm）
    
    Returns:
        车身节点ID，如果找不到返回 None
    """
    cx, cy, cz = curtain_node
    
    candidates = []
    
    for nid, (vx, vy, vz) in vehicle_nodes.items():
        # 必须在 Z 方向上方
        if vz <= cz:
            continue
        
        # 在 XY 平面范围内
        xy_dist = ((vx - cx)**2 + (vy - cy)**2)**0.5
        if xy_dist > search_radius:
            continue
        
        # 记录候选节点及其 Z 高度和 XY 距离
        candidates.append((nid, vz, xy_dist))
    
    if not candidates:
        return None
    
    # 优先选择 Z 值最高且 XY 距离最近的节点
    # 排序：先按 Z 降序，再按 XY 距离升序
    candidates.sort(key=lambda x: (-x[1], x[2]))
    
    return candidates[0][0]
