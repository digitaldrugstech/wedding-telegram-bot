#!/bin/bash
# Usage: ./scripts/announce.sh "HTML message text"
# Sends a message to all tracked group chats and pins in production chat.
# Reads BOT_TOKEN and DATABASE_URL from environment or .env file.

PRODUCTION_CHAT_ID="-1003086018945"

# Try to load from environment, then .env
if [ -z "$BOT_TOKEN" ]; then
    if [ -f ".env" ]; then
        BOT_TOKEN=$(grep -oP 'TELEGRAM_BOT_TOKEN=\K.*' .env 2>/dev/null)
    fi
fi

if [ -z "$DATABASE_URL" ]; then
    if [ -f ".env" ]; then
        DATABASE_URL=$(grep -oP 'DATABASE_URL=\K.*' .env 2>/dev/null)
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

# Get chat IDs from DB if available, otherwise fallback to production only
CHAT_IDS=()
if [ -n "$DATABASE_URL" ]; then
    DB_CHATS=$(psql "$DATABASE_URL" -t -A -c "SELECT chat_id FROM chat_activity WHERE chat_type IN ('group', 'supergroup') ORDER BY command_count DESC" 2>/dev/null)
    if [ -n "$DB_CHATS" ]; then
        while IFS= read -r cid; do
            CHAT_IDS+=("$cid")
        done <<< "$DB_CHATS"
    fi
fi

# Fallback to production chat if no DB chats found
if [ ${#CHAT_IDS[@]} -eq 0 ]; then
    CHAT_IDS=("$PRODUCTION_CHAT_ID")
    echo "No DB chats found, using production chat only"
fi

echo "Sending to ${#CHAT_IDS[@]} chat(s)..."

SENT=0
FAILED=0
PINNED=false

for CHAT_ID in "${CHAT_IDS[@]}"; do
    # Send message
    RESPONSE=$(curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -H "Content-Type: application/json" \
        -d "{\"chat_id\": ${CHAT_ID}, \"text\": $(echo "$1" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read().strip()))'), \"parse_mode\": \"HTML\"}")

    MSG_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['result']['message_id'])" 2>/dev/null)

    if [ -z "$MSG_ID" ]; then
        echo "  FAIL: chat $CHAT_ID"
        FAILED=$((FAILED + 1))
        continue
    fi

    SENT=$((SENT + 1))
    echo "  OK: chat $CHAT_ID (msg $MSG_ID)"

    # Pin only in production chat
    if [ "$CHAT_ID" = "$PRODUCTION_CHAT_ID" ]; then
        PIN_RESULT=$(curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/pinChatMessage" \
            -H "Content-Type: application/json" \
            -d "{\"chat_id\": ${CHAT_ID}, \"message_id\": ${MSG_ID}}")

        PIN_OK=$(echo "$PIN_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ok', False))" 2>/dev/null)

        if [ "$PIN_OK" = "True" ]; then
            echo "  PINNED in production"
            PINNED=true
        else
            echo "  FAILED to pin in production"
        fi
    fi

    sleep 0.1
done

echo ""
echo "Done: sent=$SENT, failed=$FAILED, pinned=$PINNED"
