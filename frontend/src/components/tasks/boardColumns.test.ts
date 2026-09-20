import { describe, expect, it } from "vitest";
import {
  addCustomColumn,
  bucketTasksByColumn,
  deleteCustomColumn,
  isCustomColumnId,
  moveColumnId,
  orderColumnCards,
  renameCustomColumn,
} from "./boardColumns";

function item(id: number) {
  return { id };
}

describe("isCustomColumnId", () => {
  it("recognises the custom: prefix only", () => {
    expect(isCustomColumnId("custom:abc")).toBe(true);
    expect(isCustomColumnId("new")).toBe(false);
    expect(isCustomColumnId("overdue")).toBe(false);
  });
});

describe("addCustomColumn", () => {
  it("appends a new id to the order and a title entry to the definitions", () => {
    const { order, customColumns } = addCustomColumn(["new", "in_progress"], {}, "Ждём клиента");
    expect(order).toHaveLength(3);
    const newId = order[2];
    expect(isCustomColumnId(newId)).toBe(true);
    expect(customColumns[newId]).toEqual({ title: "Ждём клиента" });
  });

  it("generates a distinct id on every call", () => {
    const first = addCustomColumn([], {}, "A");
    const second = addCustomColumn(first.order, first.customColumns, "B");
    expect(second.order[0]).not.toBe(second.order[1]);
  });
});

describe("renameCustomColumn", () => {
  it("replaces only the named column's title", () => {
    const result = renameCustomColumn({ "custom:a": { title: "Old" }, "custom:b": { title: "Kept" } }, "custom:a", "New");
    expect(result).toEqual({ "custom:a": { title: "New" }, "custom:b": { title: "Kept" } });
  });
});

describe("deleteCustomColumn", () => {
  it("removes the column from the order and definitions, and clears its members", () => {
    const result = deleteCustomColumn(
      ["new", "custom:a", "in_progress"],
      { "custom:a": { title: "Doomed" } },
      { "1": "custom:a", "2": "new" },
      "custom:a",
    );
    expect(result.order).toEqual(["new", "in_progress"]);
    expect(result.customColumns).toEqual({});
    expect(result.members).toEqual({ "2": "new" });
  });
});

describe("moveColumnId", () => {
  it("moves a column to a new index, keeping the rest in order", () => {
    expect(moveColumnId(["a", "b", "c", "d"], "d", 1)).toEqual(["a", "d", "b", "c"]);
    expect(moveColumnId(["a", "b", "c"], "a", 2)).toEqual(["b", "c", "a"]);
  });

  it("is a no-op for an id that isn't present", () => {
    expect(moveColumnId(["a", "b"], "z", 0)).toEqual(["a", "b"]);
  });
});

describe("bucketTasksByColumn", () => {
  it("places a task in its natural column when it has no custom override", () => {
    const tasks = [item(1), item(2)];
    const buckets = bucketTasksByColumn(tasks, ["new", "done"], {}, () => "new");
    expect(buckets.new.map((t) => t.id)).toEqual([1, 2]);
    expect(buckets.done).toEqual([]);
  });

  it("places a task in its custom column instead, when the override column still exists", () => {
    const tasks = [item(1), item(2)];
    const buckets = bucketTasksByColumn(tasks, ["new", "custom:x"], { "1": "custom:x" }, () => "new");
    expect(buckets.new.map((t) => t.id)).toEqual([2]);
    expect(buckets["custom:x"].map((t) => t.id)).toEqual([1]);
  });

  it("falls back to the natural column when the overridden custom column no longer exists", () => {
    const tasks = [item(1)];
    const buckets = bucketTasksByColumn(tasks, ["new"], { "1": "custom:gone" }, () => "new");
    expect(buckets.new.map((t) => t.id)).toEqual([1]);
  });
});

describe("orderColumnCards", () => {
  it("applies a saved manual order and appends unlisted cards at the end", () => {
    const tasks = [item(1), item(2), item(3)];
    expect(orderColumnCards(tasks, [3, 1]).map((t) => t.id)).toEqual([3, 1, 2]);
  });

  it("returns the original order when nothing is saved", () => {
    const tasks = [item(1), item(2)];
    expect(orderColumnCards(tasks, undefined).map((t) => t.id)).toEqual([1, 2]);
  });
});
