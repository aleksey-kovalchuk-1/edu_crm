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
  type TaskListItem,
  type TaskStatus,
} from "../../api/tasks";
import { RefreshError, queryFallback } from "../QueryState";
import { PlannerCard } from "./PlannerCard";
import { PlannerColumnSettings } from "./PlannerColumnSettings";
import { StatusCommentModal } from "./StatusCommentModal";
import { bucketByStatus, isValidMove, orderColumn } from "./plannerLogic";

/** dnd-kit's defaults are English-only strings — this app keeps all UI text in Russian (including
 * for screen-reader users), so both the one-time drag instructions and the live drag announcements
 * are provided in Russian, and the announcements name the actual card/column instead of a raw id. */
const SCREEN_READER_INSTRUCTIONS: ScreenReaderInstructions = {
  draggable:
    "Чтобы взять карточку, нажмите пробел. Стрелками переместите её между колонками и позициями. " +
    "Повторно нажмите пробел, чтобы отпустить, или Escape, чтобы отменить перемещение.",
};

function plannerAnnouncements(tasksById: Map<number, TaskListItem>): Announcements {
  const cardLabel = (id: UniqueIdentifier) => tasksById.get(Number(id))?.title ?? String(id);
  const columnLabel = (id: UniqueIdentifier) => {
    if (typeof id === "string" && (PLANNER_STATUSES as string[]).includes(id)) return TASK_STATUS_LABELS[id as TaskStatus];
    const over = tasksById.get(Number(id));
    return over ? TASK_STATUS_LABELS[over.status] : String(id);
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
  status,
  tasks,
  onMoveWithinColumn,
}: {
  status: TaskStatus;
  tasks: TaskListItem[];
  onMoveWithinColumn: (taskId: number, direction: -1 | 1) => void;
}) {
  const { setNodeRef } = useDroppable({ id: status });
  return (
    <div className="planner-column" ref={setNodeRef}>
      <div className="planner-column-head">
        <h3>{TASK_STATUS_LABELS[status]}</h3>
        <span className="muted">{tasks.length}</span>
      </div>
      <SortableContext items={tasks.map((t) => t.id)} strategy={verticalListSortingStrategy}>
        <ul className="planner-column-list">
          {tasks.map((t, index) => (
            <PlannerCard
              key={t.id}
              task={t}
              index={index}
              columnSize={tasks.length}
              onMoveWithinColumn={(direction) => onMoveWithinColumn(t.id, direction)}
            />
          ))}
          {!tasks.length && <li className="empty planner-column-empty">Пусто</li>}
        </ul>
      </SortableContext>
    </div>
  );
}

/**
 * Personal Kanban board (docs/design/tasks.md «Мой план»): the columns are a user-chosen subset/order
 * of the fixed task statuses (`planner_columns`), cards within a column keep a manually saved order
 * (`planner_positions`), both persisted via the shared `/tasks/preferences` endpoint. Moving a card
 * between columns is a real status change — the server's transition table is the only source of truth,
 * so an invalid drop (e.g. new → completed) is simply ignored rather than sent to the server.
 */
export function TaskPlannerView() {
  const prefs = useTaskPreferences();
  const savePrefs = useSaveTaskPreferences();
  const list = useTaskList({ scope: "mine", limit: 100, sort: "deadline" });
  const moveTask = useMoveTask();
  const [pendingMove, setPendingMove] = useState<{ task: TaskListItem; to: TaskStatus } | null>(null);

  const visibleColumns = prefs.data?.planner_columns ?? PLANNER_STATUSES;
  const positions = useMemo(() => prefs.data?.planner_positions ?? {}, [prefs.data?.planner_positions]);

  const columns = useMemo(() => {
    if (!list.data) return {} as Partial<Record<TaskStatus, TaskListItem[]>>;
    const buckets = bucketByStatus(list.data.items, visibleColumns);
    const ordered: Partial<Record<TaskStatus, TaskListItem[]>> = {};
    for (const status of visibleColumns) ordered[status] = orderColumn(buckets[status] ?? [], positions[status]);
    return ordered;
  }, [list.data, visibleColumns, positions]);

  const tasksById = useMemo(() => {
    const map = new Map<number, TaskListItem>();
    for (const tasks of Object.values(columns)) for (const t of tasks ?? []) map.set(t.id, t);
    return map;
  }, [columns]);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const fallback = queryFallback([list, prefs]);

  function saveColumnOrder(status: TaskStatus, ids: number[]) {
    savePrefs.mutate({ planner_positions: { ...positions, [status]: ids } });
  }

  function moveWithinColumn(status: TaskStatus, taskId: number, direction: -1 | 1) {
    const ids = (columns[status] ?? []).map((t) => t.id);
    const from = ids.indexOf(taskId);
    const to = from + direction;
    if (from === -1 || to < 0 || to >= ids.length) return;
    saveColumnOrder(status, arrayMove(ids, from, to));
  }

  function columnOfOverTarget(overId: string | number): TaskStatus | null {
    if (typeof overId === "string" && (PLANNER_STATUSES as string[]).includes(overId)) return overId as TaskStatus;
    return tasksById.get(Number(overId))?.status ?? null;
  }

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over) return;
    const activeTask = tasksById.get(Number(active.id));
    const toStatus = columnOfOverTarget(over.id);
    if (!activeTask || !toStatus) return;
    const fromStatus = activeTask.status;

    if (toStatus === fromStatus) {
      const ids = (columns[fromStatus] ?? []).map((t) => t.id);
      const oldIndex = ids.indexOf(activeTask.id);
      const overTask = tasksById.get(Number(over.id));
      const newIndex = overTask ? ids.indexOf(overTask.id) : ids.length - 1;
      if (oldIndex === -1 || newIndex === -1 || oldIndex === newIndex) return;
      saveColumnOrder(fromStatus, arrayMove(ids, oldIndex, newIndex));
      return;
    }

    if (!isValidMove(fromStatus, toStatus)) return;
    if (NEEDS_COMMENT.has(`${fromStatus}:${toStatus}`)) {
      setPendingMove({ task: activeTask, to: toStatus });
    } else {
      moveTask.mutate({ id: activeTask.id, to_status: toStatus, comment: "", version: activeTask.version });
    }
  }

  if (fallback) return fallback;

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
        accessibility={{ announcements: plannerAnnouncements(tasksById), screenReaderInstructions: SCREEN_READER_INSTRUCTIONS }}
      >
        <div className="planner-board">
          {visibleColumns.map((status) => (
            <PlannerColumn
              key={status}
              status={status}
              tasks={columns[status] ?? []}
              onMoveWithinColumn={(taskId, direction) => moveWithinColumn(status, taskId, direction)}
            />
          ))}
          {!visibleColumns.length && <p className="empty">Все колонки скрыты — настройте их через «Колонки плана».</p>}
        </div>
      </DndContext>
      {pendingMove && (
        <PendingMoveModal task={pendingMove.task} to={pendingMove.to} onDone={() => setPendingMove(null)} />
      )}
    </div>
  );
}
