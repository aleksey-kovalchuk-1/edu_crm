import { useState, type FormEvent } from "react";
import { useCourseApplications, type CourseApplication } from "../api/customerData";
import { Modal } from "../components/Modal";
import { queryFallback } from "../components/QueryState";

export function ApplicationsPage() {
  const [courseInput, setCourseInput] = useState("");
  const [streamInput, setStreamInput] = useState("");
  const [filters, setFilters] = useState({ course: "", stream: "" });
  const [selected, setSelected] = useState<CourseApplication | null>(null);
  const applications = useCourseApplications(filters.course, filters.stream);
  function search(event: FormEvent) { event.preventDefault(); setFilters({ course: courseInput.trim(), stream: streamInput.trim() }); }
  return <div className="customer-workspace">
    <form className="customer-toolbar" onSubmit={search}>
      <label>Курс <input value={courseInput} onChange={(event) => setCourseInput(event.target.value)} /></label>
      <label>Номер потока <input value={streamInput} onChange={(event) => setStreamInput(event.target.value)} /></label>
      <button className="primary" type="submit">Найти</button>
    </form>
    <section className="panel">{queryFallback([applications]) ?? <div className="table-wrap"><table className="data-table"><thead><tr>
      <th scope="col">Номер заявки</th><th scope="col">Курс</th><th scope="col">Поток</th>
      <th scope="col">Слушатель</th><th scope="col">Оплата</th>
    </tr></thead><tbody>{applications.data?.map((item) => <tr key={item.id}>
      <td><button className="table-link" onClick={() => setSelected(item)}>{item.external_number}</button></td>
      <td>{item.course}</td><td>{item.stream_number}</td><td>{item.learner_name}</td>
      <td><span className="badge badge-2">{item.payment_status_label}</span></td>
    </tr>)}</tbody></table>{!applications.data?.length ? <p className="empty">Заявки не найдены.</p> : null}</div>}</section>
    {selected ? <Modal title="Заявка на курс" close={() => setSelected(null)}>
      <dl className="customer-details">
        <div><dt>Номер заявки</dt><dd>{selected.external_number}</dd></div>
        <div><dt>Слушатель</dt><dd>{selected.learner_name}</dd></div>
        <div><dt>Курс</dt><dd>{selected.course}</dd></div>
        <div><dt>Номер потока</dt><dd>{selected.stream_number}</dd></div>
        <div><dt>Оплата</dt><dd>{selected.payment_status_label}</dd></div>
      </dl>
    </Modal> : null}
  </div>;
}
