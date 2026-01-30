"""
Memory MCP Tools Package.

Provides MCP tools for Memory system (Thoughts, Messages, Conversations).
"""

from memory.mcp.thought_tools import (
    AddThoughtInput,
    SearchThoughtsInput,
    add_thought_handler,
    search_thoughts_handler,
    get_thought_handler,
)

from memory.mcp.message_tools import (
    AddMessageInput,
    GetMessagesInput,
    SearchMessagesInput,
    add_message_handler,
    get_messages_handler,
    search_messages_handler,
)

from memory.mcp.conversation_tools import (
    GetConversationInput,
    SearchConversationsInput,
    ListConversationsInput,
    get_conversation_handler,
    search_conversations_handler,
    list_conversations_handler,
)

from memory.mcp.unified_tools import (
    SearchMemoriesInput,
    TraceConceptEvolutionInput,
    CheckConsistencyInput,
    UpdateThoughtEvolutionStageInput,
    search_memories_handler,
    trace_concept_evolution_handler,
    check_consistency_handler,
    update_thought_evolution_stage_handler,
)

__all__ = [
    # Thought tools
    "AddThoughtInput",
    "SearchThoughtsInput",
    "add_thought_handler",
    "search_thoughts_handler",
    "get_thought_handler",

    # Message tools
    "AddMessageInput",
    "GetMessagesInput",
    "SearchMessagesInput",
    "add_message_handler",
    "get_messages_handler",
    "search_messages_handler",

    # Conversation tools
    "GetConversationInput",
    "SearchConversationsInput",
    "ListConversationsInput",
    "get_conversation_handler",
    "search_conversations_handler",
    "list_conversations_handler",

    # Unified tools (cross-collection)
    "SearchMemoriesInput",
    "TraceConceptEvolutionInput",
    "CheckConsistencyInput",
    "UpdateThoughtEvolutionStageInput",
    "search_memories_handler",
    "trace_concept_evolution_handler",
    "check_consistency_handler",
    "update_thought_evolution_stage_handler",
]
