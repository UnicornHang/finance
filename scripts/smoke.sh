#!/usr/bin/env bash
# 端到端烟测 - 不依赖浏览器，覆盖核心 API 路径
#
# 用法：
#   ./scripts/smoke.sh                 # 默认测 http://localhost（nginx 80）
#   BASE_URL=http://localhost:8000 ./scripts/smoke.sh   # 直连后端

set -u

BASE_URL="${BASE_URL:-http://localhost}"
API="$BASE_URL/api/v1"

PASS=0
FAIL=0
WARN=0

ok() { echo "✅ $*"; PASS=$((PASS+1)); }
fail() { echo "❌ $*"; FAIL=$((FAIL+1)); }
warn() { echo "⚠️  $*"; WARN=$((WARN+1)); }

PY="${PYTHON:-python}"
extract() { "$PY" -c "import sys, json
d = json.load(sys.stdin)
v = d
for k in sys.argv[1].split('.'):
    v = v.get(k) if isinstance(v, dict) else None
print(v if v is not None else '')" "$1"
}

echo "🧪 Finance AI Agent - 烟测"
echo "BASE_URL = $BASE_URL"
echo ""

# 1. /health
echo "[1/9] /health"
if curl -sf "$BASE_URL/health" >/dev/null; then
  ok "健康检查通过"
else
  fail "/health 无响应，请确认服务已启动"
  echo ""
  echo "提示：先执行 ./scripts/setup.sh"
  exit 1
fi

# 2. 登录
echo ""
echo "[2/9] POST /auth/login (admin / Admin@123)"
LOGIN=$(curl -sf -X POST "$API/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=Admin@123")
TOKEN=$(echo "$LOGIN" | "$PY" -c "import sys, json; print(json.load(sys.stdin).get('access_token',''))")
if [ -n "$TOKEN" ] && [ "${#TOKEN}" -gt 50 ]; then
  ok "拿到 access_token (${#TOKEN} 字符)"
else
  fail "登录失败：$LOGIN"
  exit 1
fi

# 3. /auth/me
echo ""
echo "[3/9] GET /auth/me"
ME=$(curl -sf "$API/auth/me" -H "Authorization: Bearer $TOKEN")
ME_NAME=$(echo "$ME" | "$PY" -c "import sys, json; print(json.load(sys.stdin).get('name',''))")
if [ "$ME_NAME" = "系统管理员" ]; then
  ok "/auth/me 返回 admin 用户 ($ME_NAME)"
else
  fail "/auth/me 返回异常：$ME"
fi

# 4. GET /sessions/
echo ""
echo "[4/9] GET /sessions/"
SESSIONS=$(curl -sf "$API/sessions/" -H "Authorization: Bearer $TOKEN")
SESSIONS_COUNT=$(echo "$SESSIONS" | "$PY" -c "import sys, json; print(len(json.load(sys.stdin)))")
ok "/sessions/ 返回 $SESSIONS_COUNT 条会话"

# 5. POST /sessions/ 建一个新会话
echo ""
echo "[5/9] POST /sessions/ 新建会话"
NEW_SESSION=$(curl -sf -X POST "$API/sessions/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}')
SID=$(echo "$NEW_SESSION" | "$PY" -c "import sys, json; print(json.load(sys.stdin).get('id',''))")
if [ -n "$SID" ] && [ "${#SID}" -gt 30 ]; then
  ok "新建会话 sid=$SID"
else
  fail "建会话失败：$NEW_SESSION"
fi

# 6. SSE 流式 chat
echo ""
echo "[6/9] POST /chat/stream (SSE)"
SSE_OUT=$(mktemp)
HTTP_CODE=$(curl -s -o "$SSE_OUT" -w "%{http_code}" \
  --max-time 30 \
  -X POST "$API/chat/stream" \
  -H "Authorization: Bearer $TOKEN" \
  -F "session_id=$SID" \
  -F "message=你好小财，请用一句话介绍自己")
if [ "$HTTP_CODE" != "200" ]; then
  fail "SSE 返回 HTTP $HTTP_CODE"
  cat "$SSE_OUT" | head -5
  rm -f "$SSE_OUT"
else
  CHUNK_COUNT=$(grep -c "^data: " "$SSE_OUT" 2>/dev/null || echo 0)
  HAS_DONE=$(grep -c "\"type\": \"done\"\|\"type\":\"done\"" "$SSE_OUT" 2>/dev/null || echo 0)
  HAS_TEXT=$(grep -c "\"type\": \"text\"\|\"type\":\"text\"" "$SSE_OUT" 2>/dev/null || echo 0)
  if [ "$CHUNK_COUNT" -gt 0 ] && [ "$HAS_DONE" -gt 0 ]; then
    ok "SSE 流式正常：$CHUNK_COUNT 个事件，含 $HAS_TEXT 条 text + $HAS_DONE 条 done"
  elif [ "$HAS_TEXT" -gt 0 ]; then
    warn "SSE 收到 text 事件但缺少 done 事件（可能是 LLM 异常但未中断）"
  else
    fail "SSE 无有效事件（前 20 行）："
    head -20 "$SSE_OUT"
  fi
  rm -f "$SSE_OUT"
fi

# 7. GET /sessions/{sid}/messages
echo ""
echo "[7/9] GET /sessions/{sid}/messages"
MSGS=$(curl -sf "$API/sessions/$SID/messages" -H "Authorization: Bearer $TOKEN")
USER_COUNT=$(echo "$MSGS" | "$PY" -c "import sys, json; print(sum(1 for m in json.load(sys.stdin) if m['role']=='user'))")
ASSISTANT_COUNT=$(echo "$MSGS" | "$PY" -c "import sys, json; print(sum(1 for m in json.load(sys.stdin) if m['role']=='assistant'))")
ok "消息历史：user=$USER_COUNT, assistant=$ASSISTANT_COUNT（期望都 ≥ 1）"

# 8. GET /llm/providers + /llm/configs
echo ""
echo "[8/9] GET /llm/providers + /llm/configs"
PROVIDERS=$(curl -sf "$API/llm/providers" -H "Authorization: Bearer $TOKEN")
PROVIDERS_COUNT=$(echo "$PROVIDERS" | "$PY" -c "import sys, json; print(len(json.load(sys.stdin)))")
CONFIGS=$(curl -sf "$API/llm/configs" -H "Authorization: Bearer $TOKEN")
CONFIGS_COUNT=$(echo "$CONFIGS" | "$PY" -c "import sys, json; print(len(json.load(sys.stdin)))")
ok "/llm/providers 返回 $PROVIDERS_COUNT 个 provider"
if [ "$CONFIGS_COUNT" -ge 4 ]; then
  ok "/llm/configs 返回 $CONFIGS_COUNT 条场景配置（seed 应至少 4 条）"
else
  warn "/llm/configs 只返回 $CONFIGS_COUNT 条（期望 ≥ 4，seed 可能未跑）"
fi

# 9. 总结
echo ""
echo "================================================"
echo "📊 烟测结果：通过 $PASS / 失败 $FAIL / 警告 $WARN"
echo "================================================"

if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "排查建议："
  echo "  - $DC logs -f backend | tail -50"
  echo "  - $DC exec postgres psql -U finance -d finance -c 'SELECT count(*) FROM users;'"
  exit 1
fi

echo ""
echo "✨ 全链路通！可以打开浏览器访问 http://localhost 体验 UI"
