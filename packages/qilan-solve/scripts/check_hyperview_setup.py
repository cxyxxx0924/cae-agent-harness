#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Check HyperView Setup

Verify that HyperView is properly configured for d3plot rendering.

@author draven.chen <draven.chen@rccchina.com.cn>
@jira [draven/fix-hyperview-encoding]
"""

import os
import sys
from pathlib import Path

# Import the find_hyperview function from render_d3plot_gif
sys.path.insert(0, str(Path(__file__).parent))
from render_d3plot_gif import find_hyperview


def check_setup():
    """Check HyperView configuration."""
    print("=" * 60)
    print("HyperView Configuration Check")
    print("=" * 60)
    print()
    
    # 1. Check HYPERWORKS_HOME environment variable
    hyperworks_home = os.getenv('HYPERWORKS_HOME')
    print("1. HYPERWORKS_HOME environment variable:")
    if hyperworks_home:
        print(f"   ✓ Found: {hyperworks_home}")
        candidates = [os.path.join(hyperworks_home, *parts) for parts in (
            ('hwdesktop', 'hw', 'bin', 'win64', 'hw.exe'),
            ('hw', 'bin', 'win64', 'hw.exe'),
        )]
        hw_exe = next((candidate for candidate in candidates if os.path.isfile(candidate)), None)
        if hw_exe:
            print(f"   ✓ hw.exe exists: {hw_exe}")
        else:
            print("   ✗ hw.exe not found in the configured directory")
    else:
        print("   ✗ Not set")
    print()
    
    # 2. Try to find HyperView
    print("2. Searching for HyperView executable:")
    hyperview_exe = find_hyperview()
    if hyperview_exe:
        print(f"   ✓ Found: {hyperview_exe}")
        if os.path.exists(hyperview_exe):
            print(f"   ✓ File exists and is accessible")
            # Try to get file size to verify read access
            try:
                size = os.path.getsize(hyperview_exe)
                print(f"   ✓ File size: {size / (1024**2):.1f} MB")
            except Exception as e:
                print(f"   ✗ Cannot read file: {e}")
        else:
            print(f"   ✗ File does not exist")
    else:
        print("   ✗ Not found")
    print()
    
    # 3. Check system encoding
    print("3. System encoding configuration:")
    print(f"   Platform: {sys.platform}")
    try:
        import locale
        encoding = locale.getpreferredencoding()
        print(f"   Preferred encoding: {encoding}")
        if sys.platform == "win32" and encoding.lower() in ['gbk', 'gb2312', 'cp936']:
            print(f"   ✓ Chinese Windows encoding detected (GBK)")
        elif sys.platform == "win32":
            print(f"   ⚠ Non-GBK encoding on Windows: {encoding}")
    except Exception as e:
        print(f"   ✗ Cannot detect encoding: {e}")
    print()
    
    # 4. Summary
    print("=" * 60)
    print("Summary:")
    print("=" * 60)
    
    if hyperview_exe and os.path.exists(hyperview_exe):
        print("✓ HyperView is properly configured!")
        print()
        print("You can now use render_d3plot_gif.py:")
        print(f"  python scripts/render_d3plot_gif.py \\")
        print(f"    --d3plot path/to/d3plot \\")
        print(f"    --output animation.gif")
        return 0
    else:
        print("✗ HyperView is NOT configured")
        print()
        print("Please fix the configuration:")
        print()
        print("Option 1: Set HYPERWORKS_HOME environment variable")
        print("  set HYPERWORKS_HOME=C:\\Program Files\\Altair\\2024")
        print()
        print("Option 2: Manually specify path when running")
        print("  python scripts/render_d3plot_gif.py \\")
        print("    --d3plot path/to/d3plot \\")
        print("    --output animation.gif \\")
        print('    --hyperview "C:\\Program Files\\Altair\\2024\\hwdesktop\\hw\\bin\\win64\\hw.exe"')
        return 1


if __name__ == '__main__':
    sys.exit(check_setup())
