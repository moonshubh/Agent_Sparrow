#!/bin/bash

# Stage all non-test files and non-md files (except claude.md)
git ls-files --modified --deleted --others --exclude-standard | while read -r file; do
  # Skip test files
  if [[ $file == *test*.py || $file == *.test.* || $file == */test/* || $file == */tests/* || $file == *__tests__* || $file == *test_* || $file == *.spec.* || $file == *fixtures* || $file == *__mocks__* ]]; then
    echo "Skipping test file: $file"
    continue
  fi
  
  # Skip .md files except claude.md
  if [[ $file == *.md && $file != "CLAUDE.md" && $file != "claude.md" ]]; then
    echo "Skipping markdown file: $file"
    continue
  fi
  
  echo "Staging: $file"
  git add "$file"
done

echo "\nStaged changes:"
git status --porcelain
