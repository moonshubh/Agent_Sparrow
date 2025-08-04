#!/usr/bin/env python3
"""
CI validation script to ensure no local PostgreSQL dependencies remain in production code.
This script should be run as part of the CI pipeline.
"""

import os
import sys
import re
from pathlib import Path
from typing import List, Tuple

# Patterns to detect local DB dependencies
FORBIDDEN_PATTERNS = [
    r'from\s+app\.db\.connection_manager\s+import',
    r'from\s+app\.feedme\.repositories\.optimized_repository\s+import',
    r'get_connection_manager\s*\(',
    r'OptimizedFeedMeRepository',
    r'ConnectionManager',
    r'with_db_connection',
    r'from\s+app\.db\.local\s+import',
    r'from\s+app\.feedme\.search\.vector_search\s+import\s+VectorSearchEngine',
    r'from\s+app\.feedme\.search\.text_search\s+import',
    r'from\s+app\.feedme\.search\.hybrid_search_engine\s+import\s+HybridSearchEngine(?!Supabase)',
]

# Files/directories to exclude from checking
EXCLUDE_PATTERNS = [
    '*/test_*',
    '*/tests/*',
    '*/__pycache__/*',
    '*.pyc',
    '*/migrations/*',
    '*/scripts/*',
    '*/docs/*',
    '.git/*',
    'validate_no_local_db.py',  # Exclude this script itself
]

def should_check_file(file_path: Path) -> bool:
    """Check if file should be validated."""
    str_path = str(file_path)
    
    # Check exclusions
    for pattern in EXCLUDE_PATTERNS:
        if file_path.match(pattern):
            return False
    
    # Only check Python files
    return file_path.suffix == '.py'

def check_file_for_patterns(file_path: Path) -> List[Tuple[int, str, str]]:
    """Check a file for forbidden patterns."""
    violations = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.splitlines()
            
        for line_num, line in enumerate(lines, 1):
            # Skip comments
            line_stripped = line.strip()
            if line_stripped.startswith('#') or line_stripped.startswith('//'):
                continue
            
            for pattern in FORBIDDEN_PATTERNS:
                if re.search(pattern, line):
                    violations.append((line_num, pattern, line.strip()))
                    
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        
    return violations

def main():
    """Main validation function."""
    # Get project root (parent of scripts directory)
    project_root = Path(__file__).parent.parent
    
    all_violations = []
    files_checked = 0
    
    # Check all Python files in app directory
    app_dir = project_root / 'app'
    for py_file in app_dir.rglob('*.py'):
        if should_check_file(py_file):
            files_checked += 1
            violations = check_file_for_patterns(py_file)
            if violations:
                all_violations.append((py_file, violations))
    
    # Report results
    print(f"Checked {files_checked} files for local DB dependencies")
    
    if all_violations:
        print(f"\n❌ Found {len(all_violations)} files with forbidden local DB imports:\n")
        
        for file_path, violations in all_violations:
            rel_path = file_path.relative_to(project_root)
            print(f"  {rel_path}:")
            for line_num, pattern, line in violations:
                print(f"    Line {line_num}: {line}")
                print(f"    Pattern: {pattern}\n")
        
        print("\n🚫 CI FAILED: Local PostgreSQL dependencies detected!")
        print("Please update the code to use Supabase client instead.")
        sys.exit(1)
    else:
        print("\n✅ CI PASSED: No local PostgreSQL dependencies found!")
        sys.exit(0)

if __name__ == '__main__':
    main()