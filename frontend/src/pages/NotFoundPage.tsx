import { Link } from "react-router";
import { ArrowRight } from "lucide-react";
import { paths } from "../app/navigation";

export function NotFoundPage() {
  return (
    <section className="panel">
      <p className="empty">
        Такой страницы нет. Проверьте адрес или вернитесь на главную.
      </p>
      <Link className="text-button" to={paths.overview}>
        Перейти на главную <ArrowRight size={16} />
      </Link>
    </section>
  );
}
