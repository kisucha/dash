#!/bin/bash
# SessionEnd Hook — 세션 종료 시 talk_history.md에 종료 시각 기록

PROJECT_DIR="C:/Develop/Dash"
HISTORY_FILE="$PROJECT_DIR/talk_history.md"

TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")

if [ -f "$HISTORY_FILE" ]; then
    echo "" >> "$HISTORY_FILE"
    echo "<!-- session-end: $TIMESTAMP -->" >> "$HISTORY_FILE"
fi

exit 0
