import { useMemo, useState } from "react";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useDroppable,
  useSensor,
  useSensors,
  type Announcements,
  type DragEndEvent,
  type ScreenReaderInstructions,
  type UniqueIdentifier,
} from "@dnd-kit/core";
import { SortableContext, arrayMove, sortableKeyboardCoordinates, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { Plus } from "lucide-react";
import { errorText } from "../../api/client";
import {
  useMoveTaskDeadline,
  useSaveTaskPreferences,
  useTaskList,
  useTaskPreferences,
  type CustomColumn,
  type TaskFilterParams,
  type TaskListItem,
  type TaskScope,
} from "../../api/tasks";
import { Modal } from "../Modal";
import { RefreshError, queryFallback } from "../QueryState";
import { TaskCreateForm } from "../forms/TaskCreateForm";
import { AddBoardColumn } from "./AddBoardColumn";
import { BoardColumnHeader } from "./BoardColumnHeader";
import { DeadlineCard } from "./DeadlineCard";
import { bucketTasksByColumn, isCustomColumnId, orderColumnCards } from "./boardColumns";
import { DEADLINE_SYSTEM_COLUMNS, classifyDeadline, prefillDateForColumn, resolveDeadlineColumnOrder, type DeadlineColumnKey } from "./deadlineBoard";
import { useBoardColumnActions } from "./useBoardColumnActions";

const SCREEN_READER_INSTRUCTIONS: ScreenReaderInstructions = {
  draggable:
    "Чтобы взять карточку, нажмите пробел. Стрелками переместите её между колонками и позициями. " +
    "Повторно нажмите пробел, чтобы отпустить, или Escape, чтобы отменить перемещение.",
};

function deadlineAnnouncements(tasksById: Map<number, TaskListItem>, columnLabels: Record<string, string>): Announcements {
  const cardLabel = (id: UniqueIdentifier) => tasksById.get(Number(id))?.title ?? String(id);
  const columnLabel = (id: UniqueIdentifier) => {
    if (typeof id === "string" && columnLabels[id]) return columnLabels[id];
    return String(id);
  };
  return {
    onDragStart: ({ active }) => `Карточка «${cardLabel(active.id)}» взята для перемещения.`,
    onDragOver: ({ active, over }) =>
      over
        ? `Карточка «${cardLabel(active.id)}» перемещена в колонку «${columnLabel(over.id)}».`
        : `Карточка «${cardLabel(active.id)}» вне колонок.`,
    onDragEnd: ({ active, over }) =>
      over
        ? `Карточка «${cardLabel(active.id)}» отпущена в колонке «${columnLabel(over.id)}».`
        : `Карточка «${cardLabel(active.id)}» отпущена без изменений.`,
    onDragCancel: ({ active }) => `Перемещение отменено. Карточка «${cardLabel(active.id)}» возвращена на место.`,
  };
}

function DeadlineColumn({
  columnId,
  label,
  isCustom,
  tasks,
  customColumns,
  canMoveLeft,
  canMoveRight,
  onMoveLeft,
  onMoveRight,
  onRename,
  onDelete,
  onMoveWithinColumn,
  onMove,
  onCreate,
}: {
  columnId: string;
  label: string;
  isCustom: boolean;
  tasks: TaskListItem[];
  customColumns: Record<string, CustomColumn>;
  canMoveLeft: boolean;
  canMoveRight: boolean;
  onMoveLeft: () => void;
  onMoveRight: () => void;
  onRename: (title: string) => void;
  onDelete: () => void;
  onMoveWithinColumn: (taskId: number, direction: -1 | 1) => void;
  onMove: (taskId: number, toColumnId: string) => void;
  onCreate: () => void;
}) {
  const { setNodeRef } = useDroppable({ id: columnId });
  return (
    <div className="planner-column" ref={setNodeRef}>
      <BoardColumnHeader
        label={label}
        count={tasks.length}
        isCustom={isCustom}
        canMoveLeft={canMoveLeft}
        canMoveRight={canMoveRight}
        onMoveLeft={onMoveLeft}
        onMoveRight={onMoveRight}
        onRename={onRename}
        onDelete={onDelete}
      />
      <button type="button" className="text-button deadline-column-add" onClick={onCreate}>
        <Plus size={13} /> Добавить задачу
      </button>
      <SortableContext items={tasks.map((t) => t.id)} strategy={verticalListSortingStrategy}>
        <ul className="planner-column-list">
          {tasks.map((t, index) => (
            <DeadlineCard
              key={t.id}
              task={t}
              index={index}
              columnSize={tasks.length}
              currentColumnId={columnId}
              customColumns={customColumns}
              onMoveWithinColumn={(direction) => onMoveWithinColumn(t.id, direction)}
              onMove={(toColumnId) => onMove(t.id, toColumnId)}
            />
          ))}
          {!tasks.length && <li className="empty planner-column-empty">Пусто</li>}
        </ul>
      </SortableContext>
    </div>
  );
}

/**
 * "Сроки" as a horizontal Kanban board (docs/design/tasks.md, D-205): the 6 date-based columns are
 * always shown, even empty — unlike the planner they can never be hidden — plus any personal custom
 * columns (D-202/D-203, shared boardColumns.ts). Moving a card into a system column sets the task's
 * real deadline to that column's representative date (same mapping the "+" button prefills with);
 * moving into a custom column is a pure personal placement that never touches the real deadline.
 */
export function TaskDeadlineBoard({
  scope,
  search,
  filters,
}: {
  scope: TaskScope;
  search: string;
  filters: TaskFilterParams;
}) {
  const prefs = useTaskPreferences();
  const savePrefs = useSaveTaskPreferences();
  const list = useTaskList({ scope, search, ...filters, active: true, limit: 100, sort: "deadline" });
  const moveDeadline = useMoveTaskDeadline();
  const [creatingInColumn, setCreatingInColumn] = useState<string | null>(null);
  const today = useMemo(() => new Date(), []);

  const columnOrder = useMemo(() => resolveDeadlineColumnOrder(prefs.data?.deadline_columns), [prefs.data?.deadline_columns]);
  const customColumns = useMemo(() => prefs.data?.deadline_custom_columns ?? {}, [prefs.data?.deadline_custom_columns]);
  const customMembers = useMemo(() => prefs.data?.deadline_custom_members ?? {}, [prefs.data?.deadline_custom_members]);
  const positions = useMemo(() => prefs.data?.deadline_positions ?? {}, [prefs.data?.deadline_positions]);
  const columnActions = useBoardColumnActions("deadline", columnOrder, customColumns, customMembers, (patch) => savePrefs.mutate(patch));

  const columnLabels = useMemo(() => {
    const labels: Record<string, string> = {};
    for (const c of DEADLINE_SYSTEM_COLUMNS) labels[c.key] = c.label;
    for (const [id, column] of Object.entries(customColumns)) labels[id] = column.title;
    return labels;
  }, [customColumns]);

  const columns = useMemo(() => {
    if (!list.data) return {} as Record<string, TaskListItem[]>;
    const buckets = bucketTasksByColumn(list.data.items, columnOrder, customMembers, (t) => classifyDeadline(t.deadline, today));
    const ordered: Record<string, TaskListItem[]> = {};
    for (const id of columnOrder) ordered[id] = orderColumnCards(buckets[id] ?? [], positions[id]);
    return ordered;
  }, [list.data, columnOrder, customMembers, positions, today]);

  const tasksById = useMemo(() => {
    const map = new Map<number, TaskListItem>();
    for (const tasks of Object.values(columns)) for (const t of tasks) map.set(t.id, t);
    return map;
  }, [columns]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const fallback = queryFallback([list, prefs]);

  function saveColumnOrder(columnId: string, ids: number[]) {
    savePrefs.mutate({ deadline_positions: { ...positions, [columnId]: ids } });
  }

  function moveWithinColumn(columnId: string, taskId: number, direction: -1 | 1) {
    const ids = (columns[columnId] ?? []).map((t) => t.id);
    const from = ids.indexOf(taskId);
    const to = from + direction;
    if (from === -1 || to < 0 || to >= ids.length) return;
    saveColumnOrder(columnId, arrayMove(ids, from, to));
  }

  /** The single dispatcher for every cross-column move — the card's own "Переместить" select and a
   * drag-and-drop both call this. No move is ever "invalid" here (any deadline can be set), so unlike
   * the planner there's nothing to reject client-side — a failure (e.g. lacking CHANGE_DEADLINE
   * permission) simply surfaces the server's error and leaves the card where it was, since the card's
   * column is derived from query data that's never optimistically changed. */
  function handleMove(task: TaskListItem, fromColumnId: string, toColumnId: string) {
    if (fromColumnId === toColumnId) return;
    if (isCustomColumnId(toColumnId)) {
      savePrefs.mutate({ deadline_custom_members: { ...customMembers, [String(task.id)]: toColumnId } });
      return;
    }
    function clearCustomMemberIfNeeded() {
      if (!isCustomColumnId(fromColumnId)) return;
      const rest = { ...customMembers };
      delete rest[String(task.id)];
      savePrefs.mutate({ deadline_custom_members: rest });
    }
    const newDeadline = prefillDateForColumn(toColumnId as DeadlineColumnKey, today);
    moveDeadline.mutate({ id: task.id, deadline: newDeadline, version: task.version }, { onSuccess: clearCustomMemberIfNeeded });
  }

  function columnOfOverTarget(overId: string | number): string | null {
    if (typeof overId === "string" && columnOrder.includes(overId)) return overId;
    const overTask = tasksById.get(Number(overId));
    if (!overTask) return null;
    return customMembers[String(overTask.id)] ?? classifyDeadline(overTask.deadline, today);
  }

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over) return;
    const activeTask = tasksById.get(Number(active.id));
    const toColumnId = columnOfOverTarget(over.id);
    if (!activeTask || !toColumnId) return;
    const fromColumnId = customMembers[String(activeTask.id)] ?? classifyDeadline(activeTask.deadline, today);

    if (toColumnId === fromColumnId) {
      const ids = (columns[fromColumnId] ?? []).map((t) => t.id);
      const oldIndex = ids.indexOf(activeTask.id);
      const overTask = tasksById.get(Number(over.id));
      const newIndex = overTask ? ids.indexOf(overTask.id) : ids.length - 1;
      if (oldIndex === -1 || newIndex === -1 || oldIndex === newIndex) return;
      saveColumnOrder(fromColumnId, arrayMove(ids, oldIndex, newIndex));
      return;
    }
    handleMove(activeTask, fromColumnId, toColumnId);
  }

  if (fallback) return fallback;

  const creatingLabel = creatingInColumn ? columnLabels[creatingInColumn] : null;
  const creatingPrefill = creatingInColumn && !isCustomColumnId(creatingInColumn) ? prefillDateForColumn(creatingInColumn as DeadlineColumnKey, today) : null;

  return (
    <div className="planner">
      <RefreshError queries={[list, prefs]} />
      {moveDeadline.isError && (
        <p className="danger" role="alert">
          {errorText(moveDeadline.error)}
        </p>
      )}
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
        accessibility={{ announcements: deadlineAnnouncements(tasksById, columnLabels), screenReaderInstructions: SCREEN_READER_INSTRUCTIONS }}
      >
        <div className="planner-board">
          {columnOrder.map((columnId, index) => (
            <DeadlineColumn
              key={columnId}
              columnId={columnId}
              label={columnLabels[columnId] ?? columnId}
              isCustom={isCustomColumnId(columnId)}
              tasks={columns[columnId] ?? []}
              customColumns={customColumns}
              canMoveLeft={index > 0}
              canMoveRight={index < columnOrder.length - 1}
              onMoveLeft={() => columnActions.moveColumn(columnId, index - 1)}
              onMoveRight={() => columnActions.moveColumn(columnId, index + 1)}
              onRename={(title) => columnActions.renameColumn(columnId, title)}
              onDelete={() => columnActions.deleteColumn(columnId)}
              onMoveWithinColumn={(taskId, direction) => moveWithinColumn(columnId, taskId, direction)}
              onMove={(taskId, toColumnId) => {
                const task = tasksById.get(taskId);
                if (task) handleMove(task, columnId, toColumnId);
              }}
              onCreate={() => setCreatingInColumn(columnId)}
            />
          ))}
          <AddBoardColumn onAdd={columnActions.addColumn} />
        </div>
      </DndContext>
      {creatingInColumn && (
        <Modal title={`Новая задача — «${creatingLabel}»`} close={() => setCreatingInColumn(null)}>
          <TaskCreateForm
            initialDeadline={creatingPrefill}
            onCancel={() => setCreatingInColumn(null)}
            onCreated={(task) => {
              if (isCustomColumnId(creatingInColumn)) {
                savePrefs.mutate({ deadline_custom_members: { ...customMembers, [String(task.id)]: creatingInColumn } });
              }
              setCreatingInColumn(null);
            }}
          />
        </Modal>
      )}
    </div>
  );
}
