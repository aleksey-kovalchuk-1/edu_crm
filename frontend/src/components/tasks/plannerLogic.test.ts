import { describe, expect, it } from "vitest";
import type { TaskListItem } from "../../api/tasks";
import { bucketByStatus, isValidMove, orderColumn } from "./plannerLogic";

function item(id: number, status: TaskListItem["status"]): TaskListItem {
  return {
    id,
    title: `Задача ${id}`,
    status,
    priority: "normal",
    deadline: null,
    creator: null,
    assignees: [],
    university: null,
    created_at: "2026-01-01T00:00:00Z",
    version: 1,
  };
}

describe("bucketByStatus", () => {
  it("groups tasks into the visible columns only, preserving list order within each", () => {
    const tasks = [item(1, "new"), item(2, "in_progress"), item(3, "new"), item(4, "completed")];
    const buckets = bucketByStatus(tasks, ["new", "in_progress"]);
    expect(buckets.new?.map((t) => t.id)).toEqual([1, 3]);
    expect(buckets.in_progress?.map((t) => t.id)).toEqual([2]);
    expect(buckets.completed).toBeUndefined();
  });

  it("places a task in its custom column override instead of its real status column", () => {
    const tasks = [item(1, "new"), item(2, "new")];
    const buckets = bucketByStatus(tasks, ["new", "custom:waiting"], { "1": "custom:waiting" });
    expect(buckets.new.map((t) => t.id)).toEqual([2]);
    expect(buckets["custom:waiting"].map((t) => t.id)).toEqual([1]);
  });
});

describe("orderColumn", () => {
  it("returns the original order when no manual order is saved", () => {
    const tasks = [item(1, "new"), item(2, "new")];
    expect(orderColumn(tasks, undefined).map((t) => t.id)).toEqual([1, 2]);
  });

  it("applies the saved manual order and appends tasks missing from it at the end", () => {
    const tasks = [item(1, "new"), item(2, "new"), item(3, "new")];
    expect(orderColumn(tasks, [3, 1]).map((t) => t.id)).toEqual([3, 1, 2]);
  });

  it("ignores ids in the saved order that no longer belong to the column", () => {
    const tasks = [item(1, "new"), item(2, "new")];
    expect(orderColumn(tasks, [99, 2, 1]).map((t) => t.id)).toEqual([2, 1]);
  });
});

describe("isValidMove", () => {
  it("allows a move the server's transition table permits", () => {
    expect(isValidMove("new", "in_progress")).toBe(true);
  });

  it("rejects a move that skips required steps", () => {
    expect(isValidMove("new", "completed")).toBe(false);
  });

  it("rejects any move out of a terminal status", () => {
    expect(isValidMove("cancelled", "new")).toBe(false);
  });
});
