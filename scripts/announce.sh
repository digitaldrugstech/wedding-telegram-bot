#!/bin/bash
# Usage: ./scripts/announce.sh "HTML message text"
# Sends a message to the production chat and pins it.
# Reads BOT_TOKEN from environment or .env file.

CHAT_ID="-1003086018945"

# Try to load token from environment, then .env
if [ -z "$BOT_TOKEN" ]; then
    if [ -f ".env" ]; then
        BOT_TOKEN=$(grep -oP 'TELEGRAM_BOT_TOKEN=\K.*' .env 2>/dev/null)
    fi
fi

if [ -z "$BOT_TOKEN" ]; then
    echo "Error: BOT_TOKEN not set. Export it or add TELEGRAM_BOT_TOKEN to .env"
    exit 1
fi

if [ -z "$1" ]; then
    echo "Usage: $0 \"<b>Message</b> in HTML format\""
    exit 1
fi

# Send message
RESPONSE=$(curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
    -H "Content-Type: application/json" \
    -d "{\"chat_id\": ${CHAT_ID}, \"text\": $(echo "$1" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read().strip()))'), \"parse_mode\": \"HTML\"}")

# Extract message ID
MSG_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['result']['message_id'])" 2>/dev/null)

if [ -z "$MSG_ID" ]; then
    echo "Failed to send message:"
    echo "$RESPONSE" | python3 -m json.tool
    exit 1
fi

echo "Message sent (ID: $MSG_ID)"

# Pin message
PIN_RESULT=$(curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/pinChatMessage" \
    -H "Content-Type: application/json" \
    -d "{\"chat_id\": ${CHAT_ID}, \"message_id\": ${MSG_ID}}")

PIN_OK=$(echo "$PIN_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok', False))" 2>/dev/null)

if [ "$PIN_OK" = "True" ]; then
    echo "Message pinned successfully"
else
    echo "Failed to pin:"
    echo "$PIN_RESULT" | python3 -m json.tool
fi
