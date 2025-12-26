import TaskList from '@tiptap/extension-task-list';
import TaskItem from '@tiptap/extension-task-item';

export const createTaskListExtensions = () => [
  TaskList.configure({
    HTMLAttributes: { class: 'lc-task-list' },
  }),
  TaskItem.configure({
    nested: true,
  }),
];
