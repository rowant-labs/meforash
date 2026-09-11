"""Run tests that require only the published source tree and installed packages.

The explicit exclusions require acquired biblical texts, pinned tokenizer assets
or private historical experiment rows. They remain part of full test discovery;
this command reports their exclusion and does not count them as passing tests.
"""
from pathlib import Path
import unittest

ASSET_CLASSES = {
    'test_chat_model.NativeChatTests',
    'test_chat_sources.ChatSourceTests',
    'test_native_diagnostics_v1.NativeDiagnosticTests',
    'test_prepare_instruction.NativeInstructionRendererTests',
    'test_tinker_compare.ChatProfilesTests',
    'test_tinker_compare.LargeProfileTests',
    'test_tinker_compare.TmlProfileTests',
    'test_tinker_evaluate.HarmonyTests',
}
ASSET_METHODS = {
    'test_train_candidate_g.CandidateGRunnerTests.test_actual_retention_loader_uses_exact_raw12_and_v3_english16',
    'test_train_candidate_g.CandidateGRunnerTests.test_preflight_age_is_execution_only_but_expiry_is_current_at_execution',
    'test_prepare_instruction_revision.NativeRevisionTests.test_shared_renderer_keeps_once_shifted_final_only_mask',
    'test_tinker_compare.ComparisonRunTests.test_dry_run_does_not_read_key_environment_or_initialize_sdk',
    'test_tinker_evaluate.TinkerRunTests.test_dry_run_has_no_sdk_initialization_key_read_or_network',
    'test_tinker_evaluate.TinkerRunTests.test_execution_requires_prices_and_budget_before_sdk',
    'test_tinker_evaluate.TinkerRunTests.test_pinned_asset_changes_are_rejected',
    'test_train_instruction_revision.RevisionTests.test_exact_order_counts_and_validation_ids_are_verified',
    'test_hebrew.HebrewSourceBoundaryTests.test_actual_language_boundaries_and_short_aramaic_portions',
}


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def main():
    root = Path(__file__).resolve().parents[1]
    all_tests = list(flatten(unittest.defaultTestLoader.discover(str(root / 'tests'))))
    selected = [t for t in all_tests if t.id().rsplit('.', 1)[0] not in ASSET_CLASSES
                and t.id() not in ASSET_METHODS]
    print(f'Source-only suite: {len(selected)} tests selected; '
          f'{len(all_tests) - len(selected)} asset-dependent tests excluded (not counted as passes).')
    result = unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(selected))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
