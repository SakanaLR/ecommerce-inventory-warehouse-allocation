"""Safety, failure atomicity and independent scenario contracts for the CLI."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/model_assumptions_diagnostics.py'
spec = importlib.util.spec_from_file_location('diagnostics', SCRIPT)
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


@pytest.fixture
def inputs(tmp_path):
    profile = tmp_path / 'profile.csv'
    pd.DataFrame(dict(stock_code=['A', 'B', 'C'], sku_class=['Regular'] * 3,
                      avg_unit_price=[1., 1., 3.], avg_monthly_units=[30., 60., 0.],
                      std_monthly_units=[15., 30., 0.], demand_cv=[.5, .5, 0.])).to_csv(profile, index=False)
    config = tmp_path / 'config.json'
    config.write_bytes((ROOT / 'config/simulation_assumptions.json').read_bytes())
    return profile, config


def args(inputs, out, scenarios='all', seed=None):
    return diag.parse_args(['--profile', str(inputs[0]), '--config', str(inputs[1]),
                            '--output-dir', str(out), '--scenarios', scenarios]
                           + ([] if seed is None else ['--seed', str(seed)]))


def cli(inputs, out, scenarios='all'):
    return subprocess.run([sys.executable, str(SCRIPT), '--profile', str(inputs[0]),
                           '--config', str(inputs[1]), '--output-dir', str(out),
                           '--scenarios', scenarios], capture_output=True, text=True)


@pytest.mark.parametrize('suffix', ['outputs/new', 'outputs/../config/new', 'notebooks/new'])
def test_official_paths_rejected(suffix):
    with pytest.raises(SystemExit, match='Refusing'):
        diag._ensure_safe_output_dir(ROOT / suffix)


def test_symlink_to_official_directory_rejected(tmp_path):
    alias = tmp_path / 'alias'
    alias.symlink_to(ROOT / 'outputs', target_is_directory=True)
    with pytest.raises(SystemExit, match='Refusing'):
        diag._ensure_safe_output_dir(alias / 'new')


def test_existing_report_and_child_symlink_not_overwritten(inputs, tmp_path):
    out = tmp_path / 'existing'
    out.mkdir()
    (out / 'scenario_summary.csv').symlink_to(inputs[0])
    original = inputs[0].read_bytes()
    result = cli(inputs, out)
    assert result.returncode != 0
    assert 'must be new' in result.stderr
    assert inputs[0].read_bytes() == original
    assert (out / 'scenario_summary.csv').is_symlink()


@pytest.mark.parametrize('scenario', ['TYPO', 'A,', 'A,A', ''])
def test_bad_scenarios_fail_before_publication(inputs, tmp_path, scenario):
    out = tmp_path / 'result'
    result = cli(inputs, out, scenario)
    assert result.returncode != 0
    assert 'no new report published' in result.stderr
    assert not out.exists()


@pytest.mark.parametrize('problem', ['duplicate', 'missing', 'nan', 'inf', 'negative', 'empty', 'partial'])
def test_invalid_profile_fails_without_report(inputs, tmp_path, problem):
    frame = pd.read_csv(inputs[0])
    if problem == 'duplicate':
        frame.loc[1, 'stock_code'] = 'A'
    elif problem == 'missing':
        frame = frame.drop(columns='avg_unit_price')
    elif problem == 'empty':
        frame = frame.iloc[:0]
    elif problem == 'partial':
        frame['current_inventory'] = 0
    else:
        frame.loc[0, 'avg_monthly_units'] = {'nan': float('nan'), 'inf': float('inf'), 'negative': -1}[problem]
    frame.to_csv(inputs[0], index=False)
    out = tmp_path / 'result'
    with pytest.raises(SystemExit, match='no new report published'):
        diag.main(['--profile', str(inputs[0]), '--config', str(inputs[1]), '--output-dir', str(out)])
    assert not out.exists()


@pytest.mark.parametrize('problem', ['zero_days', 'nan_cost', 'negative_probability', 'unsupported', 'scenario_invalid'])
def test_invalid_config_or_late_scenario_fails_atomically(inputs, tmp_path, problem):
    config = json.loads(inputs[1].read_text())
    if problem == 'zero_days': config['days_per_month'] = 0
    if problem == 'nan_cost': config['order_quantity']['ordering_cost_gbp'] = float('nan')
    if problem == 'negative_probability': config['supplier_lead_time_days']['probabilities'][0] = -.2
    if problem == 'unsupported': config['methods']['order_quantity'] = 'top_up'
    if problem == 'scenario_invalid':
        config['safety_stock']['service_level_by_class'] = {k: .51 for k in diag.simulation.SKU_CLASSES}
    inputs[1].write_text(json.dumps(config))
    out = tmp_path / 'result'
    with pytest.raises((ValueError, AssertionError)):
        diag.run(args(inputs, out, 'A,1b'))
    assert not out.exists()


def test_write_failure_does_not_publish_partial_report(inputs, tmp_path, monkeypatch):
    original = pd.DataFrame.to_csv
    calls = []
    def fail_second(self, *a, **kw):
        calls.append(1)
        if len(calls) == 2: raise OSError('injected disk failure')
        return original(self, *a, **kw)
    monkeypatch.setattr(pd.DataFrame, 'to_csv', fail_second)
    out = tmp_path / 'result'
    with pytest.raises(OSError, match='injected'):
        diag.run(args(inputs, out))
    assert not out.exists()
    assert not list(tmp_path.glob('.model-diagnostics-*'))


def test_cli_scenarios_are_independent_deterministic_and_described(inputs, tmp_path):
    out1, out2 = tmp_path / 'run1', tmp_path / 'run2'
    assert cli(inputs, out1).returncode == 0
    assert cli(inputs, out2, '5,4b,4a,3b,3a,2b,2a,1b,1a,B,A').returncode == 0
    for filename in ['scenario_summary.csv', 'field_change_counts.csv']:
        a, b = [pd.read_csv(p / filename).sort_values('scenario').reset_index(drop=True) for p in (out1, out2)]
        pd.testing.assert_frame_equal(a, b, check_exact=True)
    for path in (out1 / 'risk_transitions').glob('*.csv'):
        assert path.read_bytes() == (out2 / 'risk_transitions' / path.name).read_bytes()
    metadata = json.loads((out1 / 'run_metadata.json').read_text())
    assert metadata['status'] == 'complete'
    assert metadata['parameter_changes']['A']['max_order_coverage_days_after'] is None
    assert metadata['scenario_configs']['B']['mode'] == 'full_regeneration'
    assert metadata['inputs']['profile_sha256'] == diag._sha256_file(inputs[0])
    assert metadata['code']['source_file_sha256']
    assert metadata['code']['untracked_file_sha256']
    assert metadata['code']['staged_diff_sha256']
    fields = pd.read_csv(out1 / 'field_change_counts.csv').set_index('scenario')
    assert fields.loc['A_fixed_inventory_uncapped', 'current_inventory_changed_skus'] == 0
    assert fields.loc['B_full_regeneration_uncapped', 'current_inventory_changed_skus'] > 0


def test_saved_baseline_verification_and_seed_override(inputs, tmp_path):
    baseline, config = diag.load_baseline(*inputs, None)
    baseline.to_csv(inputs[0], index=False)
    actual, overridden = diag.load_baseline(*inputs, 123)
    assert overridden['seed'] == 123
    expected = diag.simulation.simulate(baseline[diag.pre_simulation_columns(baseline)], overridden)
    pd.testing.assert_frame_equal(actual, expected, check_exact=True)
    baseline.loc[0, 'current_inventory'] += 1
    baseline.to_csv(inputs[0], index=False)
    with pytest.raises(AssertionError):
        diag.load_baseline(*inputs, None)


def test_metadata_tracks_staged_and_untracked_content(inputs, tmp_path, monkeypatch):
    # Isolated git repository: never stage or commit anything in the real repo.
    repo = tmp_path / 'metadata_repo'
    repo.mkdir()
    def git(*arguments):
        return subprocess.run(['git', *arguments], cwd=repo, check=True, capture_output=True)
    git('init')
    (repo / 'tracked.txt').write_text('original\n')
    git('add', 'tracked.txt')
    git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'fixture')
    (repo / 'untracked.txt').write_text('first\n')
    source = repo / 'diagnostic.py'
    source.write_text('source fixture\n')
    monkeypatch.setattr(diag, 'PROJECT_ROOT', repo)
    monkeypatch.setattr(diag, '__file__', str(source))
    before = diag.collect_run_metadata(*inputs, None)['code']
    (repo / 'tracked.txt').write_text('staged change\n')
    git('add', 'tracked.txt')
    (repo / 'untracked.txt').write_text('second\n')
    after = diag.collect_run_metadata(*inputs, None)['code']
    assert before['staged_diff_sha256'] != after['staged_diff_sha256']
    assert before['untracked_file_sha256']['untracked.txt'] != after['untracked_file_sha256']['untracked.txt']
    assert before['commit'] == after['commit']


def test_input_changed_during_calculation_is_not_published(inputs, tmp_path, monkeypatch):
    original = diag.experiment_b_full_regeneration
    def change_input(*a):
        result = original(*a)
        inputs[0].write_text(inputs[0].read_text() + '\n')
        return result
    monkeypatch.setattr(diag, 'experiment_b_full_regeneration', change_input)
    out = tmp_path / 'result'
    with pytest.raises(ValueError, match='Input changed'):
        diag.run(args(inputs, out, 'B'))
    assert not out.exists()
