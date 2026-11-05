"""
qilan-solve MCP Server

Provides MCP tools for LS-DYNA curtain airbag simulation workflow:
- Environment checking (Python, LS-DYNA, HyperView, fonts)
- K-file validation and health gates
- d3plot post-processing
- GIF rendering with HyperView
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

INSTRUCTIONS = """
MCP server for LS-DYNA curtain airbag calculation workflow (qilan-solve).

Use this server for:
- Checking environment setup (Python deps, LS-DYNA, HyperView, fonts)
- Validating K-files before solving
- Running health gates on simulation results
- Post-processing d3plot files
- Rendering GIF animations with HyperView

Always check environment first with check_environment before running other tools.
Prefer native Python scripts over shell commands when available.
"""

mcp = FastMCP("qilan-solve", instructions=INSTRUCTIONS)


def _get_skill_root() -> Path:
    """Get the qilan-solve skill root directory."""
    # src/qilan_solve_mcp/server.py -> integrations/qilan-solve
    return Path(__file__).parent.parent.parent


def _get_scripts_dir() -> Path:
    """Get the scripts directory."""
    return _get_skill_root() / "scripts"


def _run_script(script_name: str, *args: str, timeout: int = 300) -> dict:
    """
    Run a Python script from the scripts directory.
    
    Returns:
        dict with keys: success (bool), stdout (str), stderr (str), exit_code (int)
    """
    script_path = _get_scripts_dir() / script_name
    if not script_path.exists():
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Script not found: {script_path}",
            "exit_code": 1
        }
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding='gbk' if sys.platform == 'win32' else 'utf-8',
            errors='replace'
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Script timeout after {timeout}s",
            "exit_code": 124
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "exit_code": 1
        }


@mcp.tool()
def check_environment() -> dict:
    """
    Check qilan-solve environment setup.
    
    Validates:
    - Python version and required packages (numpy, matplotlib, pillow)
    - LS-DYNA solver installation
    - LSPP post-processor (optional)
    - HyperView for GIF rendering
    - Chinese fonts for plotting
    - Workspace write permissions
    
    Returns:
        dict with 'passed' (bool) and 'report' (str) keys
    """
    result = _run_script("check_environment.py")
    return {
        "passed": result["success"],
        "report": result["stdout"] + (f"\n\nErrors:\n{result['stderr']}" if result["stderr"] else "")
    }


@mcp.tool()
def check_hyperview() -> dict:
    """
    Check HyperView installation for d3plot GIF rendering.
    
    Searches common installation paths:
    - C:/Program Files/Altair/{2024,2023,2022,2021}/hwdesktop/hw/bin/win64/hw.exe
    
    Returns:
        dict with 'found' (bool), 'path' (str or None), and 'message' (str)
    """
    result = _run_script("check_hyperview_setup.py")
    
    if result["success"]:
        # Parse output to extract path
        for line in result["stdout"].splitlines():
            if "HyperView 路径:" in line or "HyperView path:" in line:
                path = line.split(":", 1)[1].strip()
                return {
                    "found": True,
                    "path": path,
                    "message": result["stdout"]
                }
    
    return {
        "found": False,
        "path": None,
        "message": result["stdout"] + (f"\n{result['stderr']}" if result["stderr"] else "")
    }


@mcp.tool()
def validate_kfile(kfile_path: str) -> dict:
    """
    Validate K-file format and structure before solving.
    
    Checks:
    - Element ID uniqueness
    - Part ID validity
    - No degenerate elements
    - No duplicate elements
    - Triangle vs quad element counts
    
    Args:
        kfile_path: Path to the K-file to validate
    
    Returns:
        dict with 'passed' (bool), 'issues' (list), and 'report' (str)
    """
    result = _run_script("qa_kfile_strict.py", kfile_path)
    
    return {
        "passed": result["success"],
        "issues": result["stderr"].splitlines() if not result["success"] else [],
        "report": result["stdout"] + (f"\n\nIssues:\n{result['stderr']}" if result["stderr"] else "")
    }


@mcp.tool()
def health_gate(
    glstat_path: str,
    matsum_path: str,
    abstat_path: str,
    total_mass: float
) -> dict:
    """
    Run post-solve health gates on simulation results.
    
    Checks:
    - Mass increase threshold
    - Hourglass energy ratio
    - Contact energy levels
    - Floor penetration
    - Inflation volume consistency
    
    Args:
        glstat_path: Path to glstat output file
        matsum_path: Path to matsum output file
        abstat_path: Path to abstat output file
        total_mass: Expected total mass in kg
    
    Returns:
        dict with 'passed' (bool), 'failures' (list), and 'report' (str)
    """
    result = _run_script(
        "k_health_gate.py",
        "--glstat", glstat_path,
        "--matsum", matsum_path,
        "--abstat", abstat_path,
        "--total-mass", str(total_mass)
    )
    
    failures = []
    if not result["success"]:
        for line in result["stdout"].splitlines():
            if "FAIL" in line or "失败" in line:
                failures.append(line)
    
    return {
        "passed": result["success"],
        "failures": failures,
        "report": result["stdout"] + (f"\n\nErrors:\n{result['stderr']}" if result["stderr"] else "")
    }


@mcp.tool()
def read_d3plot(
    d3plot_dir: str,
    state_file: Optional[str] = None,
    deck_path: Optional[str] = None,
    output_dir: Optional[str] = None
) -> dict:
    """
    Read and extract data from LS-DYNA d3plot files.
    
    Extracts:
    - Node coordinates, velocities, accelerations
    - Element connectivity and deformation
    - Fixed node verification
    - Geometry data for rendering
    
    Args:
        d3plot_dir: Directory containing d3plot files
        state_file: Specific state file (e.g., d3plot09), default: last state
        deck_path: K-file for fixed node verification (optional)
        output_dir: Output directory for extracted data (optional)
    
    Returns:
        dict with 'success' (bool), 'data_files' (list), and 'report' (str)
    """
    args = ["--geom", d3plot_dir]
    
    if state_file:
        args.extend(["--state", state_file])
    if deck_path:
        args.extend(["--deck", deck_path])
    if output_dir:
        args.extend(["--out", output_dir])
    
    result = _run_script("d3plot_reader.py", *args, timeout=600)
    
    return {
        "success": result["success"],
        "data_files": [],  # Would parse from stdout
        "report": result["stdout"] + (f"\n\nErrors:\n{result['stderr']}" if result["stderr"] else "")
    }


@mcp.tool()
def render_deployment(
    d3plot_dir: str,
    deck_path: str,
    glstat_path: str,
    output_dir: str
) -> dict:
    """
    Render deployment visualizations from d3plot results.
    
    Generates:
    - Deployment process plots
    - Final state detail plots
    - Volume/pressure curves
    - GIF animation (if HyperView available)
    
    Args:
        d3plot_dir: Directory containing d3plot files
        deck_path: K-file for reference geometry
        glstat_path: glstat file for energy/mass plots
        output_dir: Output directory for rendered images
    
    Returns:
        dict with 'success' (bool), 'output_files' (list), and 'report' (str)
    """
    result = _run_script(
        "render_deploy.py",
        "--d3dir", d3plot_dir,
        "--deck", deck_path,
        "--glstat", glstat_path,
        "--out", output_dir,
        timeout=900  # 15 minutes for rendering
    )
    
    return {
        "success": result["success"],
        "output_files": [],  # Would parse from stdout
        "report": result["stdout"] + (f"\n\nErrors:\n{result['stderr']}" if result["stderr"] else "")
    }


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
