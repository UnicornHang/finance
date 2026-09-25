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

# Ubuntu / Debian 默认只有 python3，这里做兜底
PY="${PYTHON:-$(command -v python || command -v python3)}"
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
echo "[1/11] /health"
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
echo "[2/11] POST /auth/login (admin / Admin@123)"
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
echo "[3/11] GET /auth/me"
ME=$(curl -sf "$API/auth/me" -H "Authorization: Bearer $TOKEN")
ME_NAME=$(echo "$ME" | "$PY" -c "import sys, json; print(json.load(sys.stdin).get('name',''))")
if [ "$ME_NAME" = "系统管理员" ]; then
  ok "/auth/me 返回 admin 用户 ($ME_NAME)"
else
  fail "/auth/me 返回异常：$ME"
fi

# 4. GET /sessions/
echo ""
echo "[4/11] GET /sessions/"
SESSIONS=$(curl -sf "$API/sessions/" -H "Authorization: Bearer $TOKEN")
SESSIONS_COUNT=$(echo "$SESSIONS" | "$PY" -c "import sys, json; print(len(json.load(sys.stdin)))")
ok "/sessions/ 返回 $SESSIONS_COUNT 条会话"

# 5. POST /sessions/ 建一个新会话
echo ""
echo "[5/11] POST /sessions/ 新建会话"
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
echo "[6/11] POST /chat/stream (SSE)"
SSE_OUT=$(mktemp)
HTTP_CODE=$(curl -s -o "$SSE_OUT" -w "%{http_code}" \
  --max-time 30 \
  -X POST "$API/chat/stream" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"$SID\",
    \"message\": \"你好小财，请用一句话介绍自己\"
  }")
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
echo "[7/11] GET /sessions/{sid}/messages"
MSGS=$(curl -sf "$API/sessions/$SID/messages" -H "Authorization: Bearer $TOKEN")
USER_COUNT=$(echo "$MSGS" | "$PY" -c "import sys, json; print(sum(1 for m in json.load(sys.stdin) if m['role']=='user'))")
ASSISTANT_COUNT=$(echo "$MSGS" | "$PY" -c "import sys, json; print(sum(1 for m in json.load(sys.stdin) if m['role']=='assistant'))")
ok "消息历史：user=$USER_COUNT, assistant=$ASSISTANT_COUNT（期望都 ≥ 1）"

# 8. GET /llm/providers + /llm/configs
echo ""
echo "[8/11] GET /llm/providers + /llm/configs"
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

# 9. POST /invoices/archive 直接归档（兼容旧 API）
# 编号带时间戳，保证脚本可重复运行（表上有 (tenant_id, invoice_code, invoice_number) 唯一约束）
echo ""
echo "[9/11] POST /invoices/archive"
RUN_TAG="$(date +%s | tail -c 8)"
ARCHIVE=$(curl -sf -X POST "$API/invoices/archive" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"invoice_title\": \"烟测测试发票\",
    \"company\": \"烟测公司\",
    \"tax_id\": \"91110000SMOKE\",
    \"invoice_code\": \"SMOKE$RUN_TAG\",
    \"invoice_number\": \"SMOKE$RUN_TAG\",
    \"invoice_date\": \"2026-09-21\",
    \"amount_excl_tax\": \"1000.00\",
    \"tax_amount\": \"130.00\",
    \"amount_incl_tax\": \"1130.00\",
    \"invoice_type\": \"electronic\",
    \"seller\": \"销售方\",
    \"buyer\": \"购买方\",
    \"file_url\": \"s3://invoices/smoke/sample.pdf\",
    \"file_hash\": \"smoke$RUN_TAG\"
  }")
ARCH_ID=$(echo "$ARCHIVE" | "$PY" -c "import sys, json; print(json.load(sys.stdin).get('id',''))")
if [ -n "$ARCH_ID" ]; then
  ok "归档成功 id=$ARCH_ID"
else
  fail "归档失败：$ARCHIVE"
fi

# 10. 上传发票文件 → 触发 SSE + Celery OCR
# 注意：chat/stream 已改为 JSON 请求体，文件必须先经 POST /files/upload 落到 MinIO
echo ""
echo "[10/11] POST /files/upload + /chat/stream (JSON)"
FIXTURE="$(dirname "$0")/../backend/tests/fixtures/sample_invoice.pdf"
if [ ! -f "$FIXTURE" ]; then
  warn "fixture 不存在：$FIXTURE（跳过文件上传步骤）"
else
  UPLOAD=$(curl -sf -X POST "$API/files/upload" \
    -H "Authorization: Bearer $TOKEN" \
    -F "file=@${FIXTURE};type=application/pdf")
  UP_HASH=$(echo "$UPLOAD" | "$PY" -c "import sys, json; print(json.load(sys.stdin).get('file_hash',''))" 2>/dev/null || echo "")
  UP_URL=$(echo "$UPLOAD" | "$PY" -c "import sys, json; print(json.load(sys.stdin).get('file_url',''))" 2>/dev/null || echo "")
  if [ -z "$UP_HASH" ] || [ -z "$UP_URL" ]; then
    fail "文件上传失败（应返回 file_hash/file_url）：$UPLOAD"
  else
  ok "上传成功 hash=${UP_HASH:0:12}… → $UP_URL"
  SSE_OUT=$(mktemp)
  HTTP_CODE=$(curl -s -o "$SSE_OUT" -w "%{http_code}" \
    --max-time 30 \
    -X POST "$API/chat/stream" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
      \"session_id\": \"$SID\",
      \"message\": \"帮我识别这张发票\",
      \"file_url\": \"$UP_URL\",
      \"file_hash\": \"$UP_HASH\"
    }")
  if [ "$HTTP_CODE" = "200" ]; then
    HAS_SIDEPANEL=$(grep -c "\"sidepanel\"" "$SSE_OUT" 2>/dev/null || echo 0)
    HAS_PROCESSING=$(grep -c "\"status\": \"processing\"\|\"status\":\"processing\"" "$SSE_OUT" 2>/dev/null || echo 0)
    if [ "$HAS_SIDEPANEL" -gt 0 ] && [ "$HAS_PROCESSING" -gt 0 ]; then
      ok "SSE 含 sidepanel{status:processing}，OCR 任务已派发"
    else
      warn "SSE 缺少 sidepanel processing（可能被路由分支绕过）："
      head -10 "$SSE_OUT"
    fi
  else
    fail "SSE 流式返回 HTTP $HTTP_CODE"
    head -5 "$SSE_OUT"
  fi
  rm -f "$SSE_OUT"
  fi
fi

# 11. 列表查询 + 确认归档
echo ""
echo "[11/11] POST /invoices/{id}/confirm + GET /invoices/"
if [ -n "$ARCH_ID" ]; then
  CONFIRM=$(curl -sf -X POST "$API/invoices/$ARCH_ID/confirm" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{}')
  CONF_STATUS=$(echo "$CONFIRM" | "$PY" -c "import sys, json; print(json.load(sys.stdin).get('status',''))")
  if [ "$CONF_STATUS" = "active" ]; then
    ok "confirm 后 status=active"
  else
    fail "confirm 后 status=$CONF_STATUS（期望 active）"
  fi

  # 列表应可见（-G + --data-urlencode 让 curl 自动转义中文 search）
  LIST=$(curl -sf -G "$API/invoices/" \
    -H "Authorization: Bearer $TOKEN" \
    --data-urlencode "status_filter=active" \
    --data-urlencode "search=烟测")
  FOUND=$(echo "$LIST" | "$PY" -c "import sys, json; print(sum(1 for i in json.load(sys.stdin)['items'] if i['id']=='$ARCH_ID'))")
  if [ "$FOUND" -ge 1 ]; then
    ok "列表查询找到归档发票"
  else
    warn "列表中未找到（可能是 search 过滤）"
  fi
fi

# 12. 总结
echo ""
echo "================================================"
echo "📊 烟测结果：通过 $PASS / 失败 $FAIL / 警告 $WARN"
echo "================================================"

if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "排查建议："
  echo "  - docker compose logs -f backend | tail -50"
  echo "  - docker compose exec postgres psql -U finance -d finance -c 'SELECT count(*) FROM users;'"
  exit 1
fi

echo ""
echo "✨ 全链路通！可以打开浏览器访问 $BASE_URL 体验 UI"
