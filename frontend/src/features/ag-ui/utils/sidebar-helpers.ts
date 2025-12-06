import type { ToolEvidenceUpdateEvent } from '@/services/ag-ui/event-types';
import { formatToolName, summarizeToolOutput } from './data-format';

export type SidebarTodoStatus = 'pending' | 'in_progress' | 'done' | 'completed';

export interface SidebarTodo {
  id: string;
  title?: string;
  content?: string;
  status?: SidebarTodoStatus;
  priority?: 'low' | 'medium' | 'high';
  metadata?: Record<string, unknown>;
}

export interface SidebarToolCallItem {
  id: string;
  name: string;
  status: 'running' | 'done';
  summary?: string;
  args?: string | Record<string, unknown>;
  output?: string;
}

const VALID_STATUSES: SidebarTodoStatus[] = ['pending', 'in_progress', 'done', 'completed'];

const normalizeStatus = (status?: string): SidebarTodoStatus => {
  if (!status) return 'pending';
  const normalized = status.trim().toLowerCase() as SidebarTodoStatus;
  return VALID_STATUSES.includes(normalized) ? normalized : 'pending';
};

export function normalizeTodos(todos: SidebarTodo[]) {
  return todos.map((todo) => ({
    ...todo,
    title: todo.title || todo.content || 'Task',
    status: normalizeStatus(todo.status),
  }));
}

export function computeTodoStats(normalizedTodos: ReturnType<typeof normalizeTodos>) {
  const total = normalizedTodos.length;
  const done = normalizedTodos.filter((t) => t.status === 'done' || t.status === 'completed').length;
  const inProgress = normalizedTodos.filter((t) => t.status === 'in_progress').length;
  const pending = total - done - inProgress;
  const progressPercent = total > 0 ? Math.round((done / total) * 100) : 0;
  return { total, done, inProgress, pending, progressPercent };
}

export function sortTodos(normalizedTodos: ReturnType<typeof normalizeTodos>) {
  const statusOrder: Record<string, number> = { in_progress: 0, pending: 1, done: 2, completed: 2 };
  return [...normalizedTodos].sort((a, b) => {
    const orderA = statusOrder[a.status || 'pending'] ?? 1;
    const orderB = statusOrder[b.status || 'pending'] ?? 1;
    return orderA - orderB;
  });
}

export function buildToolCallItems(
  activeTools: string[],
  toolEvidence: Record<string, ToolEvidenceUpdateEvent>
): SidebarToolCallItem[] {
  const items: SidebarToolCallItem[] = [];
  const seen = new Set<string>();

  // Active running tools
  activeTools.forEach((toolName, index) => {
    const id = `${toolName}-${index}`;
    if (seen.has(id)) return;
    seen.add(id);
    items.push({
      id,
      name: formatToolName(toolName),
      status: 'running',
    });
  });

  // Completed tool evidence
  Object.entries(toolEvidence).forEach(([key, evidence]) => {
    if (seen.has(key)) return;
    seen.add(key);
    items.push({
      id: key,
      name: formatToolName(evidence.toolName || key),
      status: 'done',
      summary: summarizeToolOutput(evidence.output ?? evidence.result ?? evidence.data ?? evidence.value),
      args: evidence.args,
      output: typeof evidence.output === 'string' ? evidence.output : undefined,
    });
  });

  return items;
}
