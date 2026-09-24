import { describe, expect, it } from "vitest";
import {
  activeFilterCount,
  filtersFromParams,
  hasExplicitFilters,
  savedFilterToPatch,
} from "./taskFilterState";

const params = (query: string) => new URLSearchParams(query);

describe("hasExplicitFilters", () => {
  it("is false when no filter dimension is present", () => {
    expect(hasExplicitFilters(params("view=list&scope=mine"))).toBe(false);
  });

  it("is true when any single filter dimension is present", () => {
    expect(hasExplicitFilters(params("status=new"))).toBe(true);
    expect(hasExplicitFilters(params("priority=high"))).toBe(true);
    expect(hasExplicitFilters(params("university_id=1"))).toBe(true);
    expect(hasExplicitFilters(params("assignee_id=5"))).toBe(true);
    expect(hasExplicitFilters(params("creator_id=5"))).toBe(true);
    expect(hasExplicitFilters(params("deadline_preset=overdue"))).toBe(true);
    expect(hasExplicitFilters(params("active=true"))).toBe(true);
    expect(hasExplicitFilters(params("has_checklist=true"))).toBe(true);
  });
});

describe("activeFilterCount", () => {
  it("is 0 with no filters", () => {
    expect(activeFilterCount(params(""))).toBe(0);
  });

  it("counts each status/priority value and each single-value filter once", () => {
    expect(activeFilterCount(params("status=new&status=in_progress&priority=high&university_id=1&deadline_preset=overdue&active=true&has_checklist=true"))).toBe(7);
    expect(activeFilterCount(params("assignee_id=5&creator_id=6&q=договор&sort=title"))).toBe(2);
  });
});

describe("filtersFromParams", () => {
  it("reads every dimension out of the URL", () => {
    expect(
      filtersFromParams(params("status=new&status=in_progress&priority=high&university_id=2&assignee_id=5&creator_id=6&deadline_preset=overdue&active=true&has_checklist=false")),
    ).toEqual({
      status: ["new", "in_progress"],
      priority: ["high"],
      university_id: 2,
      assignee_id: 5,
      creator_id: 6,
      deadline_preset: "overdue",
      active: true,
      has_checklist: false,
    });
  });

  it("gives empty/undefined values when nothing is set", () => {
    expect(filtersFromParams(params(""))).toEqual({
      status: [],
      priority: [],
      university_id: undefined,
      deadline_preset: undefined,
      active: undefined,
      has_checklist: undefined,
    });
  });
});

describe("savedFilterToPatch", () => {
  it("converts a saved filter set into a URL patch", () => {
    expect(
      savedFilterToPatch({
        status: ["new"],
        priority: [],
        university_id: 3,
        assignee_id: 5,
        deadline_preset: "today",
        active: false,
        has_checklist: undefined,
      }),
    ).toEqual({
      status: ["new"],
      priority: [],
      university_id: "3",
      assignee_id: "5",
      creator_id: null,
      deadline_preset: "today",
      active: "false",
      has_checklist: null,
    });
  });

  it("clears a dimension left empty/undefined", () => {
    expect(savedFilterToPatch({})).toEqual({
      status: [],
      priority: [],
      university_id: null,
      assignee_id: null,
      creator_id: null,
      deadline_preset: null,
      active: null,
      has_checklist: null,
    });
  });
});
