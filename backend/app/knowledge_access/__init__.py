# Knowledge Access Control Module

from app.knowledge_access.resolver import (
    KnowledgeAccessRule,
    KnowledgeBaseInfo,
    AccessResult,
    register_knowledge_base,
    get_knowledge_base,
    list_knowledge_bases,
    add_access_rule,
    remove_access_rule,
    check_access,
    get_accessible_knowledge_bases,
    grant_access,
    revoke_access,
    clear_all_rules,
    clear_all_knowledge_bases,
)

__all__ = [
    "KnowledgeAccessRule",
    "KnowledgeBaseInfo",
    "AccessResult",
    "register_knowledge_base",
    "get_knowledge_base",
    "list_knowledge_bases",
    "add_access_rule",
    "remove_access_rule",
    "check_access",
    "get_accessible_knowledge_bases",
    "grant_access",
    "revoke_access",
    "clear_all_rules",
    "clear_all_knowledge_bases",
]
