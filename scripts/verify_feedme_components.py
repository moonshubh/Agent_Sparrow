#!/usr/bin/env python3
"""
FeedMe Component Verification Script

Verifies that all redundant FeedMe components have been successfully removed
and that active components remain intact.

Exit codes:
- 0: All verification checks passed
- 1: Some redundant components still exist  
- 2: Some required components are missing
- 3: Script execution error
"""

import os
import sys
import json
from pathlib import Path
from typing import List, Dict, Any

def load_component_manifest(manifest_path: str) -> Dict[str, Any]:
    """Load component manifest JSON file"""
    try:
        with open(manifest_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading manifest {manifest_path}: {e}")
        sys.exit(3)

def check_file_exists(file_path: str) -> bool:
    """Check if a file exists"""
    # Handle both relative and absolute paths
    if not Path(file_path).exists():
        # Try with current working directory prefix
        return Path(f"./{file_path}").exists()
    return True

def verify_removed_components(remove_manifest: Dict[str, Any]) -> List[str]:
    """Verify that all components marked for removal have been deleted"""
    failures = []
    
    # Check enterprise components never integrated
    for component in remove_manifest.get('enterprise_components_never_integrated', []):
        path = component['path']
        if check_file_exists(path):
            failures.append(f"STILL EXISTS: {path} ({component['lines']} lines) - {component['reason']}")
    
    # Check unused duplicate components
    for component in remove_manifest.get('unused_duplicate_components', []):
        path = component['path']
        if check_file_exists(path):
            failures.append(f"STILL EXISTS: {path} ({component['lines']} lines) - {component['reason']}")
    
    # Check test files for removed components
    for test_file in remove_manifest.get('test_files_for_removed_components', []):
        path = test_file['path']
        if check_file_exists(path):
            failures.append(f"STILL EXISTS: {path} - {test_file['reason']}")
    
    return failures

def verify_kept_components(keep_manifest: Dict[str, Any]) -> List[str]:
    """Verify that all components marked to keep still exist"""
    failures = []
    
    # Check active components
    for component in keep_manifest.get('active_components', []):
        path = component['path']
        if not check_file_exists(path):
            failures.append(f"MISSING: {path} - {component['reason']}")
    
    # Check supporting files
    for component in keep_manifest.get('supporting_files', []):
        path = component['path']
        if not check_file_exists(path):
            failures.append(f"MISSING: {path} - {component['reason']}")
    
    return failures

def count_remaining_components() -> Dict[str, int]:
    """Count remaining FeedMe components"""
    feedme_dir = Path("frontend/components/feedme")
    if not feedme_dir.exists():
        return {"total": 0, "test_files": 0}
    
    components = list(feedme_dir.glob("*.tsx"))
    test_files = list((feedme_dir / "__tests__").glob("*.tsx")) if (feedme_dir / "__tests__").exists() else []
    
    return {
        "total": len(components),
        "test_files": len(test_files)
    }

def main():
    """Main verification function"""
    print("🔍 FeedMe Component Verification Starting...")
    print("=" * 60)
    
    # Load manifests
    remove_manifest = load_component_manifest("remove_components.json")
    keep_manifest = load_component_manifest("keep_components.json")
    
    # Verify removed components
    print("\n📋 Checking removed components...")
    removal_failures = verify_removed_components(remove_manifest)
    
    if removal_failures:
        print(f"❌ {len(removal_failures)} components still exist that should be removed:")
        for failure in removal_failures:
            print(f"  - {failure}")
        exit_code = 1
    else:
        print("✅ All redundant components successfully removed")
        exit_code = 0
    
    # Verify kept components
    print("\n📋 Checking kept components...")
    kept_failures = verify_kept_components(keep_manifest)
    
    if kept_failures:
        print(f"❌ {len(kept_failures)} required components are missing:")
        for failure in kept_failures:
            print(f"  - {failure}")
        exit_code = 2
    else:
        print("✅ All required components are present")
    
    # Summary statistics
    print("\n📊 Component Summary:")
    remaining = count_remaining_components()
    print(f"  - Active components: {remaining['total']}")
    print(f"  - Test files: {remaining['test_files']}")
    
    total_removed = remove_manifest.get('total_components_removed', 16)
    total_lines_removed = remove_manifest.get('total_lines_removed', 8500)
    print(f"  - Components removed: {total_removed}")
    print(f"  - Lines of code removed: {total_lines_removed:,}")
    
    # Calculate reduction percentages
    original_components = remaining['total'] + total_removed
    component_reduction = (total_removed / original_components) * 100 if original_components > 0 else 0
    print(f"  - Component reduction: {component_reduction:.1f}%")
    
    print("\n" + "=" * 60)
    if exit_code == 0:
        print("🎉 Verification PASSED: FeedMe component cleanup successful!")
    else:
        print("💥 Verification FAILED: Issues found in component cleanup")
    
    print(f"Exit code: {exit_code}")
    sys.exit(exit_code)

if __name__ == "__main__":
    main()