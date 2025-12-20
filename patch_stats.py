#!/usr/bin/env python3
"""
Patch getMemoryStats to count thoughts and conversations separately
"""

file_path = "C:/GitHub/Linear_coding/generations/my_project/server/services/memoryService.js"

# Lire le fichier
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Trouver la ligne qui contient "export async function getMemoryStats"
start_line = None
for i, line in enumerate(lines):
    if 'export async function getMemoryStats()' in line:
        start_line = i
        break

if start_line is None:
    print("ERROR: Could not find getMemoryStats function")
    exit(1)

# Trouver la fin de la fonction (ligne qui contient uniquement '}')
end_line = None
brace_count = 0
for i in range(start_line, len(lines)):
    if '{' in lines[i]:
        brace_count += lines[i].count('{')
    if '}' in lines[i]:
        brace_count -= lines[i].count('}')
    if brace_count == 0 and i > start_line:
        end_line = i
        break

if end_line is None:
    print("ERROR: Could not find end of getMemoryStats function")
    exit(1)

print(f"Found getMemoryStats from line {start_line+1} to {end_line+1}")

# Nouvelle fonction
new_function = '''export async function getMemoryStats() {
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
}
'''

# Conserver le commentaire JSDoc avant la fonction
comment_start = start_line - 1
while comment_start >= 0 and (lines[comment_start].strip().startswith('*') or lines[comment_start].strip().startswith('/**') or lines[comment_start].strip() == ''):
    comment_start -= 1
comment_start += 1

# Construire le nouveau fichier
new_lines = lines[:comment_start]

# Ajouter le nouveau commentaire JSDoc
new_lines.append('/**\n')
new_lines.append(' * Get basic statistics about the memory store\n')
new_lines.append(' * Counts thoughts and conversations separately using dedicated search tools\n')
new_lines.append(' *\n')
new_lines.append(' * @returns {Promise<Object>} Statistics about the memory store\n')
new_lines.append(' */\n')

# Ajouter la nouvelle fonction
new_lines.append(new_function)
new_lines.append('\n')

# Ajouter le reste du fichier
new_lines.extend(lines[end_line+1:])

# Écrire le fichier
with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"✓ Successfully patched getMemoryStats (lines {comment_start+1} to {end_line+1})")
print(f"✓ File saved: {file_path}")
