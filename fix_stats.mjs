// Script pour corriger getMemoryStats() dans memoryService.js
import fs from 'fs';

const filePath = 'C:/GitHub/Linear_coding/generations/my_project/server/services/memoryService.js';
let content = fs.readFileSync(filePath, 'utf8');

// Trouver et remplacer la fonction getMemoryStats
const oldFunction = `/**
 * Get basic statistics about the memory store
 * This is a convenience function that uses searchMemories to estimate count
 *
 * @returns {Promise<Object>} Statistics about the memory store
 */
export async function getMemoryStats() {
  const status = getMCPStatus();

  if (!isMCPConnected()) {
    return {
      connected: false,
      enabled: status.enabled,
      configured: status.configured,
      total_memories: 0,
      last_save: null,
      error: status.error,
      serverPath: status.serverPath,
    };
  }

  try {
    // Try to get a rough count by searching with a broad query
    const result = await searchMemories('*', 1);

    return {
      connected: true,
      enabled: status.enabled,
      configured: status.configured,
      total_memories: result.count || 0,
      last_save: new Date().toISOString(), // Would need to track this separately
      error: null,
      serverPath: status.serverPath,
    };
  } catch (error) {
    return {
      connected: true,
      enabled: status.enabled,
      configured: status.configured,
      total_memories: 0,
      last_save: null,
      error: error.message,
      serverPath: status.serverPath,
    };
  }
}`;

const newFunction = `/**
 * Get basic statistics about the memory store
 * Counts thoughts and conversations separately using dedicated search tools
 *
 * @returns {Promise<Object>} Statistics about the memory store
 */
export async function getMemoryStats() {
  const status = getMCPStatus();

  if (!isMCPConnected()) {
    return {
      connected: false,
      enabled: status.enabled,
      configured: status.configured,
      total_memories: 0,
      thoughts_count: 0,
      conversations_count: 0,
      last_save: null,
      error: status.error,
      serverPath: status.serverPath,
    };
  }

  try {
    // Count thoughts using search_thoughts with broad query
    let thoughtsCount = 0;
    try {
      const thoughtsResult = await callMCPTool('search_thoughts', {
        query: 'a', // Simple query that will match most thoughts
        n_results: 100
      });

      // Parse the text response to count thoughts
      const thoughtsText = thoughtsResult.content?.[0]?.text || '';
      const thoughtMatches = thoughtsText.match(/\\[Pertinence:/g);
      thoughtsCount = thoughtMatches ? thoughtMatches.length : 0;
    } catch (err) {
      console.log('[getMemoryStats] Could not count thoughts:', err.message);
    }

    // Count conversations using search_conversations with search_level="full"
    let conversationsCount = 0;
    try {
      const convsResult = await callMCPTool('search_conversations', {
        query: 'a', // Simple query that will match most conversations
        n_results: 100,
        search_level: 'full'
      });

      // Parse the text response to count conversations
      const convsText = convsResult.content?.[0]?.text || '';
      const convMatches = convsText.match(/\\[Pertinence:/g);
      conversationsCount = convMatches ? convMatches.length : 0;
    } catch (err) {
      console.log('[getMemoryStats] Could not count conversations:', err.message);
    }

    const totalMemories = thoughtsCount + conversationsCount;

    return {
      connected: true,
      enabled: status.enabled,
      configured: status.configured,
      total_memories: totalMemories,
      thoughts_count: thoughtsCount,
      conversations_count: conversationsCount,
      last_save: new Date().toISOString(), // Would need to track this separately
      error: null,
      serverPath: status.serverPath,
    };
  } catch (error) {
    return {
      connected: true,
      enabled: status.enabled,
      configured: status.configured,
      total_memories: 0,
      thoughts_count: 0,
      conversations_count: 0,
      last_save: null,
      error: error.message,
      serverPath: status.serverPath,
    };
  }
}`;

content = content.replace(oldFunction, newFunction);

fs.writeFileSync(filePath, content, 'utf8');
console.log('File updated successfully');
