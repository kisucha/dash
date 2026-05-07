#!/bin/bash
# PostToolUse Hook — Write/Edit 발생 시 code_update.md 수정 감지 및 타임스탬프 기록

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name')
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# code_update.md 또는 talk_history.md 수정 시 타임스탬프 기록
if [[ "$FILE_PATH" == *"code_update.md"* ]] || [[ "$FILE_PATH" == *"talk_history.md"* ]]; then
    TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
    echo "[$TIMESTAMP] Hook triggered: $TOOL_NAME → $FILE_PATH"
fi

exit 0
