import type { Extension } from '@tiptap/core';
import { Table } from '@tiptap/extension-table';
import TableRow from '@tiptap/extension-table-row';
import TableCell from '@tiptap/extension-table-cell';
import TableHeader from '@tiptap/extension-table-header';

export const createTableExtensions = (): Extension[] => [
  Table.configure({
    resizable: true,
  }),
  TableRow,
  TableHeader,
  TableCell,
];
