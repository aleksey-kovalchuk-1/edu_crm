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
import { errorText } from "../../api/client";
import {
  NEEDS_COMMENT,
  PLANNER_STATUSES,
  TASK_STATUS_LABELS,
  useChangeTaskStatus,
  useMoveTask,
  useSaveTaskPreferences,
  useTaskList,
  useTaskPreferences,
  type CustomColumn,
  type TaskListItem,
  type TaskStatus,
} from "../../api/tasks";
import { RefreshError, queryFallback } from "../QueryState";
import { AddBoardColumn } from "./AddBoardColumn";
import { BoardColumnHeader } from "./BoardColumnHeader";
import { PlannerCard } from "./PlannerCard";
import { PlannerColumnSettings } from "./PlannerColumnSettings";
import { StatusCommentModal } from "./StatusCommentModal";
import { bucketByStatus, isValidMove, orderColumn } from "./plannerLogic";
import { isCustomColumnId } from "./boardColumns";
import { useBoardColumnActions } from "./useBoardColumnActions";

/** dnd-kit's defaults are English-only strings — this app keeps all UI text in Russian (including
 * for screen-reader users), so both the one-time drag instructions and the live drag announcements
 * are provided in Russian, and the announcements name the actual card/column instead of a raw id. */
const SCREEN_READER_INSTRUCTIONS: ScreenReaderInstructions = {
  draggable:
    "Чтобы взять карточку, нажмите пробел. Стрелками переместите её между колонками и позициями. " +
    "Повторно нажмите пробел, чтобы отпустить, или Escape, чтобы отменить перемещение.",
};

function plannerAnnouncements(tasksById: Map<number, TaskListItem>, columnLabels: Record<string, string>): Announcements {
  const cardLabel = (id: UniqueIdentifier) => tasksById.get(Number(id))?.title ?? String(id);
  const columnLabel = (id: UniqueIdentifier) => {
    if (typeof id === "string" && columnLabels[id]) return columnLabels[id];
    const over = tasksById.get(Number(id));
    return over ? columnLabels[over.status] ?? over.status : String(id);
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

/** A raw drag (not the card's own "Переместить" select) that lands on a transition requiring a
 * comment — mounts its own status-change mutation for just that one task. */
function PendingMoveModal({ task, to, onDone }: { task: TaskListItem; to: TaskStatus; onDone: () => void }) {
  const change = useChangeTaskStatus(task.id);
  return (
    <StatusCommentModal
      pending={change.isPending}
      error={change.error}
      onCancel={onDone}
      onSubmit={(comment) => change.mutate({ to_status: to, comment, version: task.version }, { onSuccess: onDone })}
    />
  );
}

function PlannerColumn({
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
      <SortableContext items={tasks.map((t) => t.id)} strategy={verticalListSortingStrategy}>
        <ul className="planner-column-list">
          {tasks.map((t, index) => (
            <PlannerCard
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
 * Personal Kanban board (docs/design/tasks.md «Мой план»): system columns are a user-chosen
 * subset/order of the fixed task statuses (`planner_columns`), plus any personal custom columns the
 * user has added (D-202/D-203) — a custom column never changes a task's real status, it's a pure
 * placement override (`planner_custom_members`). Cards within a column keep a manually saved order
 * (`planner_positions`). Moving a card into a system column is a real status change, validated against
 * the server's transition table; moving into a custom column is unrestricted.
 */
export function TaskPlannerView() {
  const prefs = useTaskPreferences();
  const savePrefs = useSaveTaskPreferences();
  const list = useTaskList({ scope: "mine", limit: 100, sort: "deadline" });
  const moveTask = useMoveTask();
  const [pendingMove, setPendingMove] = useState<{ task: TaskListItem; to: TaskStatus } | null>(null);

  const visibleColumns = prefs.data?.planner_columns ?? PLANNER_STATUSES;
  const customColumns = useMemo(() => prefs.data?.planner_custom_columns ?? {}, [prefs.data?.planner_custom_columns]);
  const customMembers = useMemo(() => prefs.data?.planner_custom_members ?? {}, [prefs.data?.planner_custom_members]);
  const positions = useMemo(() => prefs.data?.planner_positions ?? {}, [prefs.data?.planner_positions]);
  const columnActions = useBoardColumnActions("planner", visibleColumns, customColumns, customMembers, (patch) => savePrefs.mutate(patch));

  const columnLabels = useMemo(() => {
    const labels: Record<string, string> = { ...TASK_STATUS_LABELS };
    for (const [id, column] of Object.entries(customColumns)) labels[id] = column.title;
    return labels;
  }, [customColumns]);

  const columns = useMemo(() => {
    if (!list.data) return {} as Record<string, TaskListItem[]>;
    const buckets = bucketByStatus(list.data.items, visibleColumns, customMembers);
    const ordered: Record<string, TaskListItem[]> = {};
    for (const id of visibleColumns) ordered[id] = orderColumn(buckets[id] ?? [], positions[id]);
    return ordered;
  }, [list.data, visibleColumns, customMembers, positions]);

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
    savePrefs.mutate({ planner_positions: { ...positions, [columnId]: ids } });
  }

  function moveWithinColumn(columnId: string, taskId: number, direction: -1 | 1) {
    const ids = (columns[columnId] ?? []).map((t) => t.id);
    const from = ids.indexOf(taskId);
    const to = from + direction;
    if (from === -1 || to < 0 || to >= ids.length) return;
    saveColumnOrder(columnId, arrayMove(ids, from, to));
  }

  /** The single dispatcher for every cross-column move — the card's own "Переместить" select and a
   * drag-and-drop both call this, so the rules never drift apart between the two paths. */
  function handleMove(task: TaskListItem, fromColumnId: string, toColumnId: string) {
    if (fromColumnId === toColumnId) return;
    if (isCustomColumnId(toColumnId)) {
      savePrefs.mutate({ planner_custom_members: { ...customMembers, [String(task.id)]: toColumnId } });
      return;
    }
    const toStatus = toColumnId as TaskStatus;
    if (!isValidMove(task.status, toStatus)) return;
    function clearCustomMemberIfNeeded() {
      if (!isCustomColumnId(fromColumnId)) return;
      const rest = { ...customMembers };
      delete rest[String(task.id)];
      savePrefs.mutate({ planner_custom_members: rest });
    }
    if (NEEDS_COMMENT.has(`${task.status}:${toStatus}`)) {
      setPendingMove({ task, to: toStatus });
      // The comment modal's own onSuccess (below, via PendingMoveModal) closes the modal; the
      // custom-member cleanup (if any) is only meaningful once the status change actually lands, so
      // it's re-checked from the modal's onDone rather than fired here.
    } else {
      moveTask.mutate({ id: task.id, to_status: toStatus, comment: "", version: task.version }, { onSuccess: clearCustomMemberIfNeeded });
    }
  }

  function columnOfOverTarget(overId: string | number): string | null {
    if (typeof overId === "string" && visibleColumns.includes(overId)) return overId;
    return tasksById.get(Number(overId))?.status ?? null;
  }

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over) return;
    const activeTask = tasksById.get(Number(active.id));
    const toColumnId = columnOfOverTarget(over.id);
    if (!activeTask) return;
    const fromColumnId = customMembers[String(activeTask.id)] ?? activeTask.status;
    if (!toColumnId) return;

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

  function afterCommentSuccess(task: TaskListItem, fromColumnId: string) {
    setPendingMove(null);
    if (isCustomColumnId(fromColumnId)) {
      const rest = { ...customMembers };
      delete rest[String(task.id)];
      savePrefs.mutate({ planner_custom_members: rest });
    }
  }

  return (
    <div className="planner">
      <RefreshError queries={[list, prefs]} />
      <div className="planner-toolbar">
        <PlannerColumnSettings columns={visibleColumns} onChange={(cols) => savePrefs.mutate({ planner_columns: cols })} />
      </div>
      {moveTask.isError && (
        <p className="danger" role="alert">
          {errorText(moveTask.error)}
        </p>
      )}
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
        accessibility={{ announcements: plannerAnnouncements(tasksById, columnLabels), screenReaderInstructions: SCREEN_READER_INSTRUCTIONS }}
      >
        <div className="planner-board">
          {visibleColumns.map((columnId, index) => (
            <PlannerColumn
              key={columnId}
              columnId={columnId}
              label={columnLabels[columnId] ?? columnId}
              isCustom={isCustomColumnId(columnId)}
              tasks={columns[columnId] ?? []}
              customColumns={customColumns}
              canMoveLeft={index > 0}
              canMoveRight={index < visibleColumns.length - 1}
              onMoveLeft={() => columnActions.moveColumn(columnId, index - 1)}
              onMoveRight={() => columnActions.moveColumn(columnId, index + 1)}
              onRename={(title) => columnActions.renameColumn(columnId, title)}
              onDelete={() => columnActions.deleteColumn(columnId)}
              onMoveWithinColumn={(taskId, direction) => moveWithinColumn(columnId, taskId, direction)}
              onMove={(taskId, toColumnId) => {
                const task = tasksById.get(taskId);
                if (task) handleMove(task, columnId, toColumnId);
              }}
            />
          ))}
          {!visibleColumns.length && <p className="empty">Все колонки скрыты — настройте их через «Колонки плана».</p>}
          <AddBoardColumn onAdd={columnActions.addColumn} />
        </div>
      </DndContext>
      {pendingMove && (
        <PendingMoveModal
          task={pendingMove.task}
          to={pendingMove.to}
          onDone={() => afterCommentSuccess(pendingMove.task, customMembers[String(pendingMove.task.id)] ?? pendingMove.task.status)}
        />
      )}
    </div>
  );
}
