-- 数据库初始化脚本
-- 启动时由 postgres 容器自动执行

-- 向量扩展（pgvector）
CREATE EXTENSION IF NOT EXISTS vector;

-- UUID 生成
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 中文全文检索（可选）
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 业务表由 Alembic 管理，不在此创建
-- 这里只做扩展和数据库级配置

-- 性能优化
ALTER SYSTEM SET shared_preload_libraries = 'vector';
-- 注意：shared_preload_libraries 需要重启才能生效