"""种子数据初始化脚本。

用法：
    docker-compose exec backend python scripts/seed.py
或：
    python scripts/seed.py
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# 添加项目根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.database import async_session_factory  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import KbDocument, LlmConfig, User  # noqa: E402


# 单租户 ID（私有化部署）
TENANT_ID = uuid4()


async def seed_users():
    """创建默认用户。"""
    async with async_session_factory() as session:
        # 检查是否已存在
        existing = await session.execute(select(User).where(User.account == "admin"))
        if existing.scalar_one_or_none():
            print("⚠️  用户已存在，跳过")
            return

        users = [
            User(
                tenant_id=TENANT_ID,
                name="系统管理员",
                account="admin",
                password_hash=hash_password("Admin@123"),
                role="admin",
                dept="IT",
                status="active",
            ),
            User(
                tenant_id=TENANT_ID,
                name="财务人员",
                account="finance01",
                password_hash=hash_password("Finance@123"),
                role="finance",
                dept="财务部",
                status="active",
            ),
            User(
                tenant_id=TENANT_ID,
                name="普通员工",
                account="employee01",
                password_hash=hash_password("Emp@123"),
                role="employee",
                dept="业务部",
                status="active",
            ),
        ]
        session.add_all(users)
        await session.commit()
        print(f"✅ 创建 {len(users)} 个用户")


async def seed_llm_configs():
    """创建默认 LLM 配置（从 .env 加载）。"""
    from app.config import settings

    async with async_session_factory() as session:
        existing = await session.execute(
            select(LlmConfig).where(LlmConfig.tenant_id == TENANT_ID)
        )
        if existing.scalars().first():
            print("⚠️  LLM 配置已存在，跳过")
            return

        configs = [
            LlmConfig(
                tenant_id=TENANT_ID,
                scene="chitchat",
                model=settings.llm_chitchat_model,
                provider="openai",
                base_url=settings.llm_chitchat_base_url,
                temperature=0.7,
                max_tokens=1000,
                enabled=True,
            ),
            LlmConfig(
                tenant_id=TENANT_ID,
                scene="policy_query",
                model=settings.llm_policy_model,
                provider="openai",
                base_url=settings.llm_policy_base_url,
                temperature=0.3,
                max_tokens=2000,
                enabled=True,
            ),
            LlmConfig(
                tenant_id=TENANT_ID,
                scene="ocr_post",
                model=settings.llm_ocr_model,
                provider="openai",
                base_url=settings.llm_ocr_base_url,
                temperature=0.1,
                max_tokens=2000,
                enabled=True,
            ),
            LlmConfig(
                tenant_id=TENANT_ID,
                scene="contract_review",
                model=settings.llm_contract_model,
                provider="openai",
                base_url=settings.llm_contract_base_url,
                temperature=0.2,
                max_tokens=3000,
                enabled=True,
            ),
        ]
        session.add_all(configs)
        await session.commit()
        print(f"✅ 创建 {len(configs)} 个 LLM 配置")


async def seed_kb_default_docs():
    """创建默认知识库文档。"""
    async with async_session_factory() as session:
        existing = await session.execute(
            select(KbDocument).where(KbDocument.tenant_id.is_(None))
        )
        if existing.scalars().first():
            print("⚠️  默认知识库文档已存在，跳过")
            return

        docs = [
            KbDocument(
                tenant_id=None,  # 通用文档
                title="通用合规规则",
                doc_type="rule",
                content="""
通用合同合规审查规则：

1. **盖章条款**：合同应明确约定盖章生效方式（公章 vs 合同专用章）
2. **付款周期**：标准付款周期为 30-60 天，超过 90 天需特别审批
3. **违约责任**：必须包含违约金条款，建议比例为合同金额 10-30%
4. **争议解决**：应明确约定管辖法院或仲裁机构
5. **合同金额**：必须以人民币计价且大小写一致
6. **有效期**：起止日期明确，建议不超过 3 年
7. **不可抗力**：建议包含不可抗力条款
8. **知识产权**：涉及技术/软件的合同需明确知识产权归属
""",
                status="active",
                version=1,
            ),
            KbDocument(
                tenant_id=None,
                title="差旅补贴标准",
                doc_type="policy",
                content="""
差旅补贴标准（人民币/天）：

| 城市 | 住宿 | 餐补 | 交通 |
|---|---|---|---|
| 一线城市（北京/上海/广州/深圳） | 500 | 100 | 100 |
| 二线城市 | 400 | 80 | 80 |
| 三线及以下 | 300 | 60 | 60 |

出差申请流程：
1. 出差前 3 天提交申请
2. 部门负责人审批
3. 出差后 7 天内提交报销
""",
                status="active",
                version=1,
            ),
        ]
        session.add_all(docs)
        await session.commit()
        print(f"✅ 创建 {len(docs)} 个默认知识库文档")
        print("⚠️  注意：默认文档未向量化，需要在后台触发向量化")


async def main():
    """主入口。"""
    print("🌱 开始种子数据初始化...")
    print(f"   Tenant ID: {TENANT_ID}")
    print("")

    await seed_users()
    await seed_llm_configs()
    await seed_kb_default_docs()

    print("")
    print("✨ 种子数据初始化完成！")


if __name__ == "__main__":
    asyncio.run(main())