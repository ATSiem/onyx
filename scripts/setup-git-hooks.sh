#!/bin/bash

# Script to set up Git hooks for automated testing
# Based on James Shore's best practices for internal quality

set -e  # Exit on error

ROOT_DIR="$(git rev-parse --show-toplevel)"
HOOKS_DIR="$ROOT_DIR/.git/hooks"
SCRIPTS_DIR="$ROOT_DIR/scripts"

# Make scripts executable
chmod +x "$SCRIPTS_DIR/comprehensive-test-suite.sh"
chmod +x "$SCRIPTS_DIR/pre-merge-check.sh"

# Create pre-commit hook
cat > "$HOOKS_DIR/pre-commit" << 'EOF'
#!/bin/bash

echo "Running pre-commit tests..."

# Store the current branch and changes
STASH_NAME="pre-commit-$(date +%s)"
git stash push -q --keep-index --include-untracked --message "$STASH_NAME"

# Run the comprehensive test suite
"$(git rev-parse --show-toplevel)/scripts/comprehensive-test-suite.sh"
RESULT=$?

# Restore the stashed changes
STASH_ID=$(git stash list | grep "$STASH_NAME" | cut -d: -f1)
if [ -n "$STASH_ID" ]; then
    git stash pop -q "$STASH_ID"
fi

# If tests failed, abort the commit
if [ $RESULT -ne 0 ]; then
    echo "❌ Pre-commit tests failed. Commit aborted."
    exit 1
fi

exit 0
EOF

# Create pre-merge-commit hook
cat > "$HOOKS_DIR/pre-merge-commit" << 'EOF'
#!/bin/bash

echo "Running pre-merge tests..."

# Run pre-merge checks
"$(git rev-parse --show-toplevel)/scripts/pre-merge-check.sh"
RESULT=$?

# If tests failed, abort the merge
if [ $RESULT -ne 0 ]; then
    echo "❌ Pre-merge tests failed. Merge aborted."
    exit 1
fi

exit 0
EOF

# Create post-merge hook
cat > "$HOOKS_DIR/post-merge" << 'EOF'
#!/bin/bash

echo "Running post-merge tests..."

# Run comprehensive test suite
"$(git rev-parse --show-toplevel)/scripts/comprehensive-test-suite.sh"
RESULT=$?

# If tests failed, warn but don't abort (merge already completed)
if [ $RESULT -ne 0 ]; then
    echo "⚠️ WARNING: Post-merge tests failed."
    echo "Please fix the issues or consider reverting the merge with 'git reset --hard ORIG_HEAD'"
fi

exit 0
EOF

# Make hooks executable
chmod +x "$HOOKS_DIR/pre-commit"
chmod +x "$HOOKS_DIR/pre-merge-commit"
chmod +x "$HOOKS_DIR/post-merge"

echo "✅ Git hooks successfully installed:"
echo "  - pre-commit: Runs tests before each commit"
echo "  - pre-merge-commit: Runs pre-merge checks before merging"
echo "  - post-merge: Runs tests after merging and warns if tests fail"
echo
echo "These hooks will help maintain internal quality as described in James Shore's article." 