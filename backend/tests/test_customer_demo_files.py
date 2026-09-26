import importlib.util
from pathlib import Path

import pytest

from app.customer_imports import read_customer_file


def test_synthetic_demo_files_match_customer_contracts(tmp_path):
    script = Path(__file__).resolve().parents[2] / 'scripts' / 'generate-customer-demo-files.py'
    spec = importlib.util.spec_from_file_location('customer_demo', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    paths = module.generate(tmp_path)
    for kind, path in zip(('vendors', 'learners', 'applications'), paths):
        parsed = read_customer_file(kind, path.name, path.read_bytes())
        assert parsed.template_version == f'customer-{kind}-v1'
        assert parsed.unmapped_headers == []
        assert len(parsed.rows) == (2 if kind == 'applications' else 1)
    assert len(read_customer_file('learners', paths[1].name, paths[1].read_bytes()).mapping) == 30
    with pytest.raises(FileExistsError):
        module.generate(tmp_path)
