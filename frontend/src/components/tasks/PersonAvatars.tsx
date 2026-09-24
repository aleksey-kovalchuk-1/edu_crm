import type { PersonRef } from "../../api/types";
import { initials } from "../../lib/format";

/**
 * People as overlapping initials, with every name in the accessible label and tooltip. One person
 * also shows the name next to the avatar; more show the first `max` avatars plus a "+N" counter.
 */
export function PersonAvatars({ people, max = 3 }: { people: PersonRef[]; max?: number }) {
  if (!people.length) return <span className="muted">—</span>;
  const names = people.map((p) => p.full_name).join(", ");
  const shown = people.slice(0, max);
  const rest = people.length - shown.length;
  return (
    <span className="person-avatars" title={names} aria-label={names}>
      <span className="avatar-stack" aria-hidden="true">
        {shown.map((p) => (
          <span key={p.id} className="avatar avatar-sm">
            {initials(p.full_name)}
          </span>
        ))}
        {rest > 0 && <span className="avatar avatar-sm avatar-more">+{rest}</span>}
      </span>
      {people.length === 1 && <span className="person-name" aria-hidden="true">{people[0].full_name}</span>}
    </span>
  );
}
