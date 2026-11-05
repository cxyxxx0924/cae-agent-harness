#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
d3plot to H3D Converter

Convert LS-DYNA d3plot results to HyperWorks H3D format using HyperView batch mode.
H3D format provides much better compression than raw d3plot files.

@author draven.chen <draven.chen@rccchina.com.cn>
@jira [draven/add-download-loading-state]
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from render_d3plot_gif import find_hyperview as find_hyperview_executable


def find_hyperview():
    """
    Find HyperView batch executable.
    
    @return Path to HyperView batch executable or None
    """
    found = find_hyperview_executable()
    return Path(found) if found else None


def create_hvscript(d3plot_path, h3d_output, temp_script):
    """
    Create HyperView TCL script for d3plot to H3D conversion.
    
    @param d3plot_path Path to d3plot file
    @param h3d_output Path for output H3D file
    @param temp_script Path for temporary TCL script
    """
    script_content = f"""# HyperView batch script: d3plot to H3D

# Load d3plot results
*createstartupfile "C:/temp_startup.mvw" 0
*readfile "{d3plot_path.as_posix()}" "LS-DYNA" 0

# Export to H3D
*h3dexportfile "{h3d_output.as_posix()}" 0 1 0 0 "" "" 0

# Exit
*quit 1
"""
    
    temp_script.write_text(script_content, encoding='utf-8')


def convert_d3plot_to_h3d(d3plot_dir, output_h3d, hyperview_exe=None):
    """
    Convert d3plot results to H3D format.
    
    @param d3plot_dir Directory containing d3plot files
    @param output_h3d Output H3D file path
    @param hyperview_exe Optional path to HyperView executable
    @return True if conversion succeeded
    """
    # Find main d3plot file
    d3plot_main = d3plot_dir / "d3plot"
    if not d3plot_main.exists():
        print(f"Error: d3plot file not found in {d3plot_dir}", file=sys.stderr)
        return False
    
    # Find HyperView if not provided
    if hyperview_exe is None:
        hyperview_exe = find_hyperview()
        if hyperview_exe is None:
            print("Error: HyperView executable not found", file=sys.stderr)
            print("Please install HyperWorks or specify the path with --hyperview", file=sys.stderr)
            return False
    
    print(f"Using HyperView: {hyperview_exe}")
    print(f"Converting {d3plot_main} to {output_h3d}")
    
    # Create temporary TCL script
    temp_script = d3plot_dir / "temp_convert.tcl"
    try:
        create_hvscript(d3plot_main, output_h3d, temp_script)
        
        # Run HyperView in batch mode
        cmd = [
            str(hyperview_exe),
            "-tcl",
            str(temp_script),
            "-b"
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            encoding='utf-8' if sys.platform != "win32" else 'gbk',
            errors='replace',
            cwd=str(d3plot_dir)
        )
        
        if result.returncode != 0:
            print(f"Error: HyperView conversion failed", file=sys.stderr)
            print(f"stdout: {result.stdout}", file=sys.stderr)
            print(f"stderr: {result.stderr}", file=sys.stderr)
            return False
        
        if not output_h3d.exists():
            print(f"Error: H3D file was not created", file=sys.stderr)
            return False
        
        # Report file sizes
        d3plot_size = sum(f.stat().st_size for f in d3plot_dir.glob("d3plot*") if f.is_file())
        h3d_size = output_h3d.stat().st_size
        compression_ratio = (1 - h3d_size / d3plot_size) * 100 if d3plot_size > 0 else 0
        
        print(f"Conversion successful")
        print(f"  d3plot total: {d3plot_size / (1024**2):.1f} MB")
        print(f"  H3D output: {h3d_size / (1024**2):.1f} MB")
        print(f"  Compression: {compression_ratio:.1f}%")
        
        return True
        
    finally:
        # Clean up temporary script
        if temp_script.exists():
            temp_script.unlink()


def main():
    parser = argparse.ArgumentParser(
        description="Convert LS-DYNA d3plot results to HyperWorks H3D format"
    )
    parser.add_argument(
        "--d3plot-dir",
        type=Path,
        required=True,
        help="Directory containing d3plot files"
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output H3D file path"
    )
    parser.add_argument(
        "--hyperview",
        type=Path,
        help="Path to HyperView executable"
    )
    
    args = parser.parse_args()
    
    success = convert_d3plot_to_h3d(args.d3plot_dir, args.output, args.hyperview)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
