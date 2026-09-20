# Finance Backend

FastAPI 后端服务 - 企业财务 AI Agent 平台。

## 启动

```bash
# 方式一：Docker
docker-compose up backend

# 方式二：本地
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

## 目录结构

```
backend/
├── app/
│   ├── api/v1/        # REST API 路由
│   ├── agent/         # Agent 编排（LangChain）
│   │   ├── tools/     # LangChain Tools
│   │   └── memory/    # 摘要 + 实体抽取
│   ├── core/          # 基础设施（安全、异常、DB）
│   ├── models/        # SQLAlchemy ORM 模型
│   ├── schemas/       # Pydantic DTO
│   ├── services/      # 业务服务（OCR/RAG/LLM/存储）
│   ├── tasks/         # Celery 异步任务
│   ├── config.py      # 配置加载
│   ├── deps.py        # FastAPI 依赖注入
│   └── main.py        # FastAPI 入口
├── alembic/           # 数据库迁移
├── tests/             # 单元 + 集成测试
├── pyproject.toml     # 依赖管理
└── Dockerfile
```

## 数据库迁移

```bash
# 生成迁移
alembic revision --autogenerate -m "add table"

# 应用
alembic upgrade head

# 回滚
alembic downgrade -1

# 查看历史
alembic history
```

## 测试

```bash
# 全部测试
pytest

# 覆盖率
pytest --cov=app --cov-report=html

# 单一文件
pytest tests/test_health.py
```

## 代码规范

```bash
# Lint
ruff check app/

# Type Check
mypy app/

# 安全扫描
bandit -r app/
```

## API 文档

启动后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/api/v1/openapi.json