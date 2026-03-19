#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Taskbolt SaaS Migration Script

Migrates existing single-tenant Taskbolt data to multi-tenant SaaS format.

Usage:
    python migrate-to-saas.py \
        --source ~/.taskbolt \
        --tenant-id tenant_abc123 \
        --tenant-name "My Company" \
        --admin-email admin@company.com \
        --admin-password <password>

This script will:
1. Read existing config.json, chats.json, jobs.json
2. Create tenant and admin user in database
3. Migrate all data with tenant_id assigned
4. Import agent configurations
5. Import chat history
6. Import scheduled jobs
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ============================================================================
# MIGRATION CONFIGURATION
# ============================================================================

class MigrationConfig:
    """Configuration for migration."""
    
    def __init__(
        self,
        source_dir: str,
        tenant_id: str,
        tenant_name: str,
        tenant_slug: str,
        admin_email: str,
        admin_password: str,
        admin_name: str = "Admin",
        plan: str = "PROFESSIONAL",
        database_url: Optional[str] = None,
    ):
        self.source_dir = Path(source_dir).expanduser()
        self.tenant_id = tenant_id
        self.tenant_name = tenant_name
        self.tenant_slug = tenant_slug
        self.admin_email = admin_email
        self.admin_password = admin_password
        self.admin_name = admin_name
        self.plan = plan
        self.database_url = database_url or os.environ.get("DATABASE_URL")
        
        # Validate
        if not self.source_dir.exists():
            raise ValueError(f"Source directory does not exist: {self.source_dir}")
        if not self.database_url:
            raise ValueError("DATABASE_URL must be provided")


# ============================================================================
# DATA READERS
# ============================================================================

def read_json_file(path: Path) -> Optional[Dict[str, Any]]:
    """Read JSON file if it exists."""
    if not path.exists():
        logger.warning(f"File not found: {path}")
        return None
    
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def read_text_file(path: Path) -> Optional[str]:
    """Read text file if it exists."""
    if not path.exists():
        return None
    
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class SourceDataReader:
    """Reads data from existing Taskbolt installation."""
    
    def __init__(self, source_dir: Path):
        self.source_dir = source_dir
        self.config: Optional[Dict] = None
        self.chats: Optional[Dict] = None
        self.jobs: Optional[Dict] = None
        self.sessions_dir = source_dir / "sessions"
        self.memory_dir = source_dir / "memory"
    
    def load_all(self) -> None:
        """Load all source data files."""
        logger.info(f"Loading source data from {self.source_dir}")
        
        self.config = read_json_file(self.source_dir / "config.json")
        self.chats = read_json_file(self.source_dir / "chats.json")
        self.jobs = read_json_file(self.source_dir / "jobs.json")
        
        logger.info("Source data loaded successfully")
    
    def get_agents(self) -> List[Dict[str, Any]]:
        """Extract agent configurations."""
        agents = []
        
        if not self.config:
            return agents
        
        # Check for multi-agent structure
        agents_config = self.config.get("agents", {})
        profiles = agents_config.get("profiles", {})
        
        for agent_id, profile in profiles.items():
            workspace_dir = Path(profile.get("workspace_dir", "")).expanduser()
            agent_config_path = workspace_dir / "agent.json"
            
            agent_data = {
                "id": str(uuid4()),
                "external_id": agent_id,
                "name": profile.get("name", agent_id.title()),
                "description": profile.get("description", ""),
            }
            
            # Load agent-specific config
            agent_config = read_json_file(agent_config_path)
            if agent_config:
                agent_data.update({
                    "channels": agent_config.get("channels", {}),
                    "mcp": agent_config.get("mcp", {}),
                    "tools": agent_config.get("tools", {}),
                    "security": agent_config.get("security", {}),
                    "running": agent_config.get("running", {}),
                    "llm_routing": agent_config.get("llmRouting", {}),
                })
            else:
                # Use root config as fallback
                agent_data.update({
                    "channels": self.config.get("channels", {}),
                    "mcp": self.config.get("mcp", {}),
                    "tools": self.config.get("tools", {}),
                    "security": self.config.get("security", {}),
                })
            
            agents.append(agent_data)
        
        # If no agents found, create default agent
        if not agents:
            agents.append({
                "id": str(uuid4()),
                "external_id": "default",
                "name": "Default Agent",
                "description": "Migrated from single-tenant Taskbolt",
                "channels": self.config.get("channels", {}) if self.config else {},
                "mcp": self.config.get("mcp", {}) if self.config else {},
                "tools": self.config.get("tools", {}) if self.config else {},
                "security": self.config.get("security", {}) if self.config else {},
            })
        
        return agents
    
    def get_chats(self) -> List[Dict[str, Any]]:
        """Extract chat history."""
        chats = []
        
        if not self.chats:
            return chats
        
        for chat in self.chats.get("chats", []):
            chats.append({
                "id": str(uuid4()),
                "external_id": chat.get("id", str(uuid4())),
                "name": chat.get("name", "Migrated Chat"),
                "channel": chat.get("channel", "console"),
                "session_id": chat.get("session_id", ""),
                "user_id": chat.get("user_id", ""),
                "status": chat.get("status", "idle"),
                "created_at": chat.get("created_at"),
                "updated_at": chat.get("updated_at"),
            })
        
        return chats
    
    def get_jobs(self) -> List[Dict[str, Any]]:
        """Extract scheduled jobs."""
        jobs = []
        
        if not self.jobs:
            return jobs
        
        for job in self.jobs.get("jobs", []):
            jobs.append({
                "id": str(uuid4()),
                "external_id": job.get("id", str(uuid4())),
                "name": job.get("name", "Migrated Job"),
                "enabled": job.get("enabled", True),
                "cron_expression": job.get("schedule", {}).get("cron", "0 0 * * *"),
                "timezone": job.get("schedule", {}).get("timezone", "UTC"),
                "task_type": job.get("task_type", "text"),
                "task_config": job.get("request", {}),
                "dispatch_config": job.get("dispatch", {}),
            })
        
        return jobs
    
    def get_sessions(self) -> List[Dict[str, Any]]:
        """Extract session files."""
        sessions = []
        
        if not self.sessions_dir.exists():
            return sessions
        
        for session_file in self.sessions_dir.glob("*.json"):
            session_data = read_json_file(session_file)
            if session_data:
                sessions.append({
                    "file_name": session_file.name,
                    "data": session_data,
                })
        
        return sessions
    
    def get_memory(self) -> List[Dict[str, Any]]:
        """Extract memory files."""
        memories = []
        
        if not self.memory_dir.exists():
            return memories
        
        for memory_file in self.memory_dir.glob("*.json"):
            memory_data = read_json_file(memory_file)
            if memory_data:
                memories.append({
                    "file_name": memory_file.name,
                    "data": memory_data,
                })
        
        return memories
    
    def get_md_files(self) -> Dict[str, str]:
        """Extract markdown files (AGENTS.md, SOUL.md, PROFILE.md)."""
        md_files = {}
        
        for md_name in ["AGENTS.md", "SOUL.md", "PROFILE.md", "MEMORY.md", "HEARTBEAT.md"]:
            content = read_text_file(self.source_dir / md_name)
            if content:
                md_files[md_name] = content
        
        return md_files


# ============================================================================
# DATABASE WRITER
# ============================================================================

class DatabaseWriter:
    """Writes migrated data to SaaS database."""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.prisma = None
    
    async def connect(self) -> None:
        """Connect to database."""
        from prisma import Prisma
        
        self.prisma = Prisma()
        await self.prisma.connect()
        logger.info("Connected to database")
    
    async def disconnect(self) -> None:
        """Disconnect from database."""
        if self.prisma:
            await self.prisma.disconnect()
            logger.info("Disconnected from database")
    
    async def create_tenant(
        self,
        tenant_id: str,
        name: str,
        slug: str,
        plan: str,
    ) -> Any:
        """Create tenant record."""
        tenant = await self.prisma.tenant.create(
            data={
                "id": tenant_id,
                "name": name,
                "slug": slug,
                "plan": plan,
                "maxAgents": 10 if plan == "PROFESSIONAL" else 3,
                "maxUsers": 25 if plan == "PROFESSIONAL" else 5,
                "maxStorageBytes": 107374182400 if plan == "PROFESSIONAL" else 10737418240,
            }
        )
        logger.info(f"Created tenant: {tenant_id}")
        return tenant
    
    async def create_admin_user(
        self,
        tenant_id: str,
        email: str,
        name: str,
        firebase_uid: Optional[str] = None,
    ) -> Any:
        """Create admin user."""
        user = await self.prisma.user.create(
            data={
                "tenantId": tenant_id,
                "firebaseUid": firebase_uid or f"migrated_{uuid4().hex[:16]}",
                "email": email,
                "displayName": name,
                "role": "OWNER",
            }
        )
        logger.info(f"Created admin user: {email}")
        return user
    
    async def create_agent(
        self,
        tenant_id: str,
        agent_data: Dict[str, Any],
    ) -> Any:
        """Create agent record."""
        agent = await self.prisma.agent.create(
            data={
                "id": agent_data["id"],
                "tenantId": tenant_id,
                "externalId": agent_data["external_id"],
                "name": agent_data["name"],
                "description": agent_data.get("description", ""),
                "channels": agent_data.get("channels", {}),
                "mcp": agent_data.get("mcp", {}),
                "tools": agent_data.get("tools", {}),
                "security": agent_data.get("security", {}),
                "running": agent_data.get("running", {}),
                "llmRouting": agent_data.get("llm_routing", {}),
            }
        )
        logger.info(f"Created agent: {agent_data['external_id']}")
        return agent
    
    async def create_chat(
        self,
        tenant_id: str,
        agent_id: str,
        user_id: str,
        chat_data: Dict[str, Any],
    ) -> Any:
        """Create chat record."""
        chat = await self.prisma.chat.create(
            data={
                "id": chat_data["id"],
                "tenantId": tenant_id,
                "agentId": agent_id,
                "userId": user_id,
                "externalId": chat_data["external_id"],
                "name": chat_data["name"],
                "channel": chat_data.get("channel", "console"),
                "sessionId": chat_data.get("session_id", f"console:{user_id}"),
                "status": chat_data.get("status", "IDLE"),
            }
        )
        return chat
    
    async def create_message(
        self,
        tenant_id: str,
        chat_id: str,
        role: str,
        content: str,
        created_at: Optional[str] = None,
    ) -> Any:
        """Create message record."""
        message = await self.prisma.message.create(
            data={
                "tenantId": tenant_id,
                "chatId": chat_id,
                "role": role.upper(),
                "content": content,
                "createdAt": datetime.fromisoformat(created_at) if created_at else datetime.utcnow(),
            }
        )
        return message
    
    async def create_job(
        self,
        tenant_id: str,
        agent_id: str,
        job_data: Dict[str, Any],
    ) -> Any:
        """Create job record."""
        job = await self.prisma.job.create(
            data={
                "id": job_data["id"],
                "tenantId": tenant_id,
                "agentId": agent_id,
                "externalId": job_data["external_id"],
                "name": job_data["name"],
                "enabled": job_data.get("enabled", True),
                "cronExpression": job_data.get("cron_expression", "0 0 * * *"),
                "timezone": job_data.get("timezone", "UTC"),
                "taskType": job_data.get("task_type", "text"),
                "taskConfig": job_data.get("task_config", {}),
                "dispatchConfig": job_data.get("dispatch_config", {}),
            }
        )
        logger.info(f"Created job: {job_data['name']}")
        return job
    
    async def create_audit_log(
        self,
        tenant_id: str,
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        details: Dict[str, Any],
    ) -> Any:
        """Create audit log entry."""
        return await self.prisma.auditlog.create(
            data={
                "tenantId": tenant_id,
                "userId": user_id,
                "action": action,
                "resourceType": resource_type,
                "resourceId": resource_id,
                "newValues": details,
            }
        )


# ============================================================================
# MIGRATION EXECUTOR
# ============================================================================

class MigrationExecutor:
    """Executes the full migration process."""
    
    def __init__(self, config: MigrationConfig):
        self.config = config
        self.reader = SourceDataReader(config.source_dir)
        self.writer = DatabaseWriter(config.database_url)
        
        # IDs
        self.tenant_id = config.tenant_id
        self.admin_user_id: Optional[str] = None
        self.agent_id_map: Dict[str, str] = {}  # old_id -> new_id
    
    async def run(self) -> Dict[str, Any]:
        """Run the complete migration."""
        logger.info("=" * 60)
        logger.info("Starting Taskbolt SaaS Migration")
        logger.info("=" * 60)
        
        results = {
            "tenant": None,
            "user": None,
            "agents": [],
            "chats": 0,
            "messages": 0,
            "jobs": [],
            "errors": [],
        }
        
        try:
            # Load source data
            self.reader.load_all()
            
            # Connect to database
            await self.writer.connect()
            
            # 1. Create tenant
            tenant = await self.writer.create_tenant(
                tenant_id=self.tenant_id,
                name=self.config.tenant_name,
                slug=self.config.tenant_slug,
                plan=self.config.plan,
            )
            results["tenant"] = {"id": tenant.id, "name": tenant.name}
            
            # 2. Create admin user
            user = await self.writer.create_admin_user(
                tenant_id=self.tenant_id,
                email=self.config.admin_email,
                name=self.config.admin_name,
            )
            self.admin_user_id = user.id
            results["user"] = {"id": user.id, "email": user.email}
            
            # 3. Migrate agents
            agents = self.reader.get_agents()
            for agent_data in agents:
                try:
                    agent = await self.writer.create_agent(
                        tenant_id=self.tenant_id,
                        agent_data=agent_data,
                    )
                    self.agent_id_map[agent_data["external_id"]] = agent.id
                    results["agents"].append({
                        "id": agent.id,
                        "external_id": agent.externalId,
                        "name": agent.name,
                    })
                except Exception as e:
                    results["errors"].append(f"Agent migration error: {e}")
            
            # 4. Migrate chats and messages
            default_agent_id = list(self.agent_id_map.values())[0] if self.agent_id_map else None
            if default_agent_id:
                chats = self.reader.get_chats()
                for chat_data in chats:
                    try:
                        chat = await self.writer.create_chat(
                            tenant_id=self.tenant_id,
                            agent_id=default_agent_id,
                            user_id=self.admin_user_id,
                            chat_data=chat_data,
                        )
                        results["chats"] += 1
                        
                        # Migrate messages from session files
                        sessions = self.reader.get_sessions()
                        for session in sessions:
                            if chat_data.get("session_id") in session["file_name"]:
                                for msg in session["data"].get("messages", []):
                                    await self.writer.create_message(
                                        tenant_id=self.tenant_id,
                                        chat_id=chat.id,
                                        role=msg.get("role", "user"),
                                        content=msg.get("content", ""),
                                    )
                                    results["messages"] += 1
                    except Exception as e:
                        results["errors"].append(f"Chat migration error: {e}")
            
            # 5. Migrate jobs
            jobs = self.reader.get_jobs()
            for job_data in jobs:
                try:
                    agent_id = default_agent_id or list(self.agent_id_map.values())[0]
                    job = await self.writer.create_job(
                        tenant_id=self.tenant_id,
                        agent_id=agent_id,
                        job_data=job_data,
                    )
                    results["jobs"].append({
                        "id": job.id,
                        "name": job.name,
                    })
                except Exception as e:
                    results["errors"].append(f"Job migration error: {e}")
            
            # 6. Create audit log
            await self.writer.create_audit_log(
                tenant_id=self.tenant_id,
                user_id=self.admin_user_id,
                action="migration.completed",
                resource_type="tenant",
                resource_id=self.tenant_id,
                details={
                    "agents_count": len(results["agents"]),
                    "chats_count": results["chats"],
                    "messages_count": results["messages"],
                    "jobs_count": len(results["jobs"]),
                },
            )
            
            logger.info("=" * 60)
            logger.info("Migration completed successfully!")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"Migration failed: {e}", exc_info=True)
            results["errors"].append(f"Migration failed: {e}")
            raise
        
        finally:
            await self.writer.disconnect()
        
        return results


# ============================================================================
# CLI ENTRY POINT
# ============================================================================

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Migrate Taskbolt single-tenant data to SaaS multi-tenant format"
    )
    
    parser.add_argument(
        "--source",
        required=True,
        help="Source directory (existing Taskbolt data, e.g., ~/.taskbolt)",
    )
    parser.add_argument(
        "--tenant-id",
        required=True,
        help="New tenant ID (e.g., tenant_abc123)",
    )
    parser.add_argument(
        "--tenant-name",
        required=True,
        help="Tenant/company name",
    )
    parser.add_argument(
        "--tenant-slug",
        required=False,
        help="Tenant URL slug (default: derived from name)",
    )
    parser.add_argument(
        "--admin-email",
        required=True,
        help="Admin user email",
    )
    parser.add_argument(
        "--admin-name",
        default="Admin",
        help="Admin user name (default: Admin)",
    )
    parser.add_argument(
        "--plan",
        default="PROFESSIONAL",
        choices=["FREE", "STARTER", "PROFESSIONAL", "ENTERPRISE"],
        help="Subscription plan (default: PROFESSIONAL)",
    )
    parser.add_argument(
        "--database-url",
        help="Database URL (or set DATABASE_URL env var)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes",
    )
    
    return parser.parse_args()


async def main() -> None:
    """Main entry point."""
    args = parse_args()
    
    # Generate slug from name if not provided
    slug = args.tenant_slug or args.tenant_name.lower().replace(" ", "-").replace("_", "-")
    
    config = MigrationConfig(
        source_dir=args.source,
        tenant_id=args.tenant_id,
        tenant_name=args.tenant_name,
        tenant_slug=slug,
        admin_email=args.admin_email,
        admin_password="",  # Will be set via Firebase
        admin_name=args.admin_name,
        plan=args.plan,
        database_url=args.database_url,
    )
    
    if args.dry_run:
        logger.info("DRY RUN - No changes will be made")
        reader = SourceDataReader(config.source_dir)
        reader.load_all()
        
        logger.info(f"Would migrate:")
        logger.info(f"  - Tenant: {config.tenant_name} ({slug})")
        logger.info(f"  - User: {config.admin_email}")
        logger.info(f"  - Agents: {len(reader.get_agents())}")
        logger.info(f"  - Chats: {len(reader.get_chats())}")
        logger.info(f"  - Jobs: {len(reader.get_jobs())}")
        logger.info(f"  - Sessions: {len(reader.get_sessions())}")
        return
    
    executor = MigrationExecutor(config)
    results = await executor.run()
    
    # Print summary
    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    print(f"Tenant: {results['tenant']}")
    print(f"User: {results['user']}")
    print(f"Agents: {len(results['agents'])}")
    print(f"Chats: {results['chats']}")
    print(f"Messages: {results['messages']}")
    print(f"Jobs: {len(results['jobs'])}")
    
    if results["errors"]:
        print(f"\nErrors: {len(results['errors'])}")
        for error in results["errors"]:
            print(f"  - {error}")


if __name__ == "__main__":
    asyncio.run(main())
