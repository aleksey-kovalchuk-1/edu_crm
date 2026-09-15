import { useState } from "react";
import { useLaunches, useTasks } from "../api/queries";
import { RefreshError, queryFallback } from "../components/QueryState";
import { SearchToolbar } from "../components/SearchToolbar";
import { TaskList } from "../components/TaskList";
import { matches } from "../lib/format";

export function TasksPage() {
  const [search, setSearch] = useState("");
  const tasks = useTasks();
  const launches = useLaunches();
  const queries = [tasks, launches];
  const fallback = queryFallback(queries);
  const taskList = tasks.data;
  const launchList = launches.data;
  if (fallback || !taskList || !launchList) return fallback;

  const filtered = taskList.filter((t) =>
    matches(`${t.title} ${t.owner}`, search),
  );
  return (
    <>
      <RefreshError queries={queries} />
      <SearchToolbar
        search={search}
        onSearch={setSearch}
        count={filtered.length}
      />
      <section className="panel">
        <TaskList rows={filtered} launches={launchList} />
      </section>
    </>
  );
}
