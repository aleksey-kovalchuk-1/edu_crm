import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { useUniversities } from "../../api/catalogs";
import type { University } from "../../api/types";
import { paths, taskPath, universityPath } from "../../app/navigation";
import { Modal } from "../../components/Modal";
import { RefreshError, queryFallback } from "../../components/QueryState";
import { TaskCreateForm } from "../../components/forms/TaskCreateForm";
import { UniversityForm } from "../../components/forms/UniversityForm";

export function SettingsUniversitiesPage() {
  const navigate = useNavigate();
  const universities = useUniversities();
  const [adding, setAdding] = useState(false);
  const [created, setCreated] = useState<University | null>(null);
  const [creatingTask, setCreatingTask] = useState(false);

  return (
    <>
      <section className="panel">
        <div className="section-head">
          <div>
            <h2>Вузы в работе</h2>
            <p>Добавьте вуз после первого контакта. Он сразу появится в выборе для задач.</p>
          </div>
          <button type="button" className="primary" onClick={() => setAdding(true)}>Добавить вуз</button>
        </div>
        {created && (
          <div role="status">
            <p>Добавлен вуз «<Link to={universityPath(created.id)}>{created.name}</Link>». По нему уже можно ставить задачи.</p>
            <button type="button" className="secondary" onClick={() => setCreatingTask(true)}>
              Создать задачу по вузу
            </button>
          </div>
        )}
        {queryFallback([universities]) ?? (
          <>
            <RefreshError queries={[universities]} />
            <p className="muted">Доступных вузов: {universities.data?.length ?? 0}</p>
            {universities.data?.length ? (
              <ul>
                {universities.data.map((university) => (
                  <li key={university.id}><Link to={universityPath(university.id)}>{university.name}</Link></li>
                ))}
              </ul>
            ) : <p className="muted">Пока нет доступных вузов.</p>}
          </>
        )}
        <Link className="text-button" to={paths.universities}>Открыть каталог вузов</Link>
      </section>
      {adding && (
        <Modal title="Новое учебное заведение" close={() => setAdding(false)}>
          <UniversityForm onDone={() => setAdding(false)} onSaved={setCreated} />
        </Modal>
      )}
      {creatingTask && created && (
        <Modal title="Новая задача" close={() => setCreatingTask(false)}>
          <TaskCreateForm
            initialUniversityId={created.id}
            initialUniversityName={created.name}
            onCancel={() => setCreatingTask(false)}
            onCreated={(task) => navigate(taskPath(task.id))}
          />
        </Modal>
      )}
    </>
  );
}
