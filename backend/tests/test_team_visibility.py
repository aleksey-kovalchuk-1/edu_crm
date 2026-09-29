"""«Видят все КАМ» (owner request 2026-09-29): heads and administrators decide on the university card whether every KAM
sees a university, or only the KAMs assigned to it."""
from test_catalog_api import create_university, head, manager  # noqa: F401 (fixtures)


def test_a_head_shares_a_university_with_every_kam_and_takes_it_back(head, manager):  # noqa: F811
    university = create_university(head)
    assert university['team_visible_to_managers'] is False
    assert manager.get(f"/api/v1/universities/{university['id']}").status_code == 404

    shared = head.patch(f"/api/v1/universities/{university['id']}", json={'team_visible_to_managers': True})
    assert shared.status_code == 200, shared.text
    assert shared.json()['team_visible_to_managers'] is True
    assert manager.get(f"/api/v1/universities/{university['id']}").status_code == 200
    assert university['id'] in [u['id'] for u in manager.get('/api/v1/universities').json()]

    head.patch(f"/api/v1/universities/{university['id']}", json={'team_visible_to_managers': False})
    assert manager.get(f"/api/v1/universities/{university['id']}").status_code == 404


def test_a_kam_cannot_change_who_sees_a_university(head, manager):  # noqa: F811
    university = create_university(head)
    head.patch(f"/api/v1/universities/{university['id']}", json={'team_visible_to_managers': True})
    response = manager.patch(f"/api/v1/universities/{university['id']}", json={'team_visible_to_managers': False})
    assert response.status_code == 403
    assert head.get(f"/api/v1/universities/{university['id']}").json()['team_visible_to_managers'] is True
