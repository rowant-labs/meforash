import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from bibleprep import prepare_instruction as prep


REVISION = 'a' * 40


def fixture(chapter=2, number=7, language='hbo'):
    identifier = f'oshb:Gen.{chapter}.{number}'
    record = {'id': identifier, 'source_id': 'oshb', 'book': 'Gen', 'chapter': chapter,
              'verse': number, 'language': language, 'text_layer': 'main/ketiv',
              'text': 'בְּרֵאשִׁ֖ית ἀρχή\u0301', 'tokens': [{'id': 'word1'}]}
    refs = [{'source_id': 'oshb', 'passage': f'Gen.{chapter}.{number}',
             'revision': REVISION, 'url': prep.source_url('oshb', 'Gen', REVISION)}]
    example = {'id': f'H{chapter}_{number}', 'language': language, 'category': 'translation',
               'source_refs': refs, 'prompt': 'Translate this wording.', 'answer': 'In the beginning.',
               'support_notes': 'Checked source wording; distinguish phrase from full sentence.',
               'author': 'author_ai', 'reviewer': 'reviewer_ai', 'review_status': 'ai_source_checked',
               'review_sources': [refs[0]['url']], 'chapter_keys': [f'oshb:Gen.{chapter}']}
    example['reviewed_content_sha256'] = prep.content_hash(example)
    return example, {identifier: record}, {'oshb': {'revision': REVISION}}


class InstructionSourceTests(unittest.TestCase):
    def test_source_excerpt_exact_unicode_and_review_content_hash(self):
        e, records, identities = fixture()
        evidence = prep.validate_example(e, records, identities, {'oshb:Gen.1'})
        self.assertEqual(evidence.splitlines()[1], records['oshb:Gen.2.7']['text'])
        e['evidence'] = evidence
        e['reviewed_content_sha256'] = prep.content_hash(e)
        self.assertEqual(prep.validate_example(e, records, identities, set()), evidence)
        e['answer'] += ' Edited after review.'
        with self.assertRaisesRegex(ValueError, 're-review'):
            prep.validate_example(e, records, identities, set())

    def test_review_cannot_be_draft_self_review_or_missing_support(self):
        e, records, identities = fixture()
        for field, value in [('review_status', 'draft'), ('reviewer', 'author_ai'), ('review_sources', [])]:
            changed = copy.deepcopy(e)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                prep.validate_example(changed, records, identities, set())

    def test_mismatched_revision_word_or_evidence_is_rejected(self):
        e, records, identities = fixture()
        for update in [lambda x: x['source_refs'][0].update(revision='b' * 40),
                       lambda x: x.update(source_word_ids=['different']),
                       lambda x: x.update(evidence='Normalized or paraphrased text'),
                       lambda x: x.update(chapter_keys=['oshb:Gen.3'])]:
            changed = copy.deepcopy(e)
            update(changed)
            changed['reviewed_content_sha256'] = prep.content_hash(changed)
            with self.assertRaises(ValueError):
                prep.validate_example(changed, records, identities, set())

    def test_no_evidence_examples_still_enforce_chapter_exclusion(self):
        e, records, identities = fixture()
        e['evidence_mode'] = 'none'
        e['reviewed_content_sha256'] = prep.content_hash(e)
        with self.assertRaisesRegex(ValueError, 'overlaps frozen evaluation'):
            prep.validate_example(e, records, identities, {'oshb:Gen.2'})

    def test_missing_duplicate_and_supplemental_readings_not_silently_combined(self):
        e, records, identities = fixture()
        for refs in [e['source_refs'] * 2, [{**e['source_refs'][0], 'passage': 'Gen.2.7-8'}]]:
            with self.assertRaises(ValueError):
                prep.build_evidence(refs, records, identities)
        records['oshb:Gen.2.7']['alternatives'] = [{'text': 'alternative'}]
        with self.assertRaisesRegex(ValueError, 'layer schema'):
            prep.build_evidence(e['source_refs'], records, identities)

    def test_exclusion_inventory_has_no_eval_questions_or_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'manifests').mkdir()
            path = root / 'manifests/exclusion.json'
            base = {'schema_version': 1, 'status': 'frozen', 'evaluation_sha256': 'f' * 64,
                    'chapter_keys': ['oshb:Gen.1']}
            path.write_text(json.dumps(base))
            self.assertEqual(prep.load_exclusion(root, 'manifests/exclusion.json')[0], {'oshb:Gen.1'})
            for update in [{'status': 'draft'}, {'expected_behavior': 'secret answer'}, {'chapter_keys': []}]:
                path.write_text(json.dumps({**base, **update}))
                with self.assertRaises(ValueError):
                    prep.load_exclusion(root, 'manifests/exclusion.json')

    def test_connected_chapters_stay_in_one_split(self):
        examples = [{'id': f'E{i:03}', 'chapter_keys': [f'oshb:Gen.{i + 1}']} for i in range(120)]
        examples[0]['chapter_keys'] += examples[1]['chapter_keys']
        examples[2]['chapter_keys'] += examples[1]['chapter_keys']
        selected = prep.split_examples(examples)
        train = {c for e in selected['train'] for c in e['chapter_keys']}
        validation = {c for e in selected['validation'] for c in e['chapter_keys']}
        self.assertFalse(train & validation)
        self.assertGreaterEqual(len(selected['train']), 100)
        self.assertTrue(selected['validation'])
        self.assertEqual(selected, prep.split_examples(list(reversed(examples))))
        with self.assertRaisesRegex(ValueError, 'connected'):
            prep.split_examples(examples, ['oshb:Gen.1'])

    def test_paths_remain_private_and_portable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ['../outside.jsonl', '/absolute/path', 'runs/../outside.jsonl']:
                with self.assertRaises(ValueError):
                    prep.relative_path(root, name, under='runs')
            self.assertEqual(prep.relative_path(root, 'runs/reviewed.jsonl', under='runs'), root.resolve() / 'runs/reviewed.jsonl')


class NativeInstructionRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.renderer = prep.InstructionRenderer()

    def test_real_native_mask_shift_prefix_answer_and_stop(self):
        answer = 'The expression means “in the beginning.” Hebrew: בְּרֵאשִׁ֖ית.'
        row = self.renderer.render('Translate this wording.', answer, 'Exact evidence: בְּרֵאשִׁ֖ית')
        prep.validate_sequence(row)
        full = row['input_ids'] + [row['target_ids'][-1]]
        predicted = full[row['prompt_token_count']:]
        rendered = self.renderer.tokenizer.native.decode(predicted)
        self.assertIn(answer, rendered)
        self.assertTrue(rendered.startswith('<|message_model|><|content_text|>'))
        self.assertTrue(rendered.endswith('<|end_message|><|content_model_end_sampling|>'))
        self.assertEqual(row['target_ids'][-1], 200006)
        self.assertEqual(row['weights'], [0.] * (row['prompt_token_count'] - 1) + [1.] * (len(row['input_ids']) - row['prompt_token_count'] + 1))
        self.assertNotIn('<|channel_analysis|>', rendered)

    def test_no_evidence_mode_does_not_render_support(self):
        row = self.renderer.render('Reflect on the question.', 'A checked reflection.', 'UNIQUE_UNRENDERED_SOURCE', 'none')
        decoded = self.renderer.tokenizer.native.decode(row['input_ids'])
        self.assertNotIn('UNIQUE_UNRENDERED_SOURCE', decoded)
        self.assertIn('Thinking effort level: 0.7', decoded)

    def test_end_to_end_offline_preparation_and_rehashed_token_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for subdir in ('manifests', 'runs', 'data/processed/oshb', 'data/processed/sblgnt'):
                (root / subdir).mkdir(parents=True)
            for relative in prep.CODE_FILES:
                path = root / relative
                path.parent.mkdir(exist_ok=True)
                path.write_text('fixture code')
            examples, source_records = [], {}
            for index in range(120):
                e, records, _ = fixture(chapter=index // 3 + 1, number=index % 3 + 1)
                examples.append(e)
                source_records.update(records)
            paths = {source: root / f'data/processed/{source}/verses.jsonl' for source in ('oshb', 'sblgnt')}
            paths['oshb'].write_bytes(b''.join(prep.json_bytes(r) + b'\n' for r in source_records.values()))
            paths['sblgnt'].write_bytes(prep.json_bytes({'id':'sblgnt:Mark.1.1','source_id':'sblgnt','book':'Mark','chapter':1,'verse':1,'language':'grc','text':'λόγος'}) + b'\n')
            (root / 'manifests/oshb.json').write_text(json.dumps({'pinned_commit':REVISION,'prepared_artifact':{'sha256':prep.raw.original.sha256(paths['oshb'])}}))
            (root / 'manifests/sblgnt.json').write_text(json.dumps({'revision':REVISION,'prepared_outputs':{'verses.jsonl':{'sha256':prep.raw.original.sha256(paths['sblgnt'])}}}))
            (root / 'manifests/exclusion.json').write_text(json.dumps({'schema_version':1,'status':'frozen','evaluation_sha256':'f'*64,'chapter_keys':['sblgnt:Acts.17']}))
            (root / 'runs/reviewed.jsonl').write_bytes(b''.join(prep.json_bytes(e) + b'\n' for e in examples))
            with mock.patch.object(prep, 'InstructionRenderer', return_value=self.renderer):
                report = prep.prepare('runs/reviewed.jsonl', 'manifests/exclusion.json', root=root)
                result = prep.verify_prepared(root, report)
                self.assertEqual(sum(len(rows) for rows in result.values()),120)
                self.assertGreaterEqual(len(result['train']),100)
                path = root / report['artifacts']['train']['path']
                rows = prep.read_rows(path)
                row = rows[0]
                index = row['prompt_token_count'] + 2
                row['input_ids'][index] = 123
                row['target_ids'][index - 1] = 123
                path.write_bytes(b''.join(prep.json_bytes(r) + b'\n' for r in rows))
                report['artifacts']['train']['sha256'] = prep.raw.original.sha256(path)
                with self.assertRaisesRegex(ValueError,'exact reviewed native rendering'):
                    prep.verify_prepared(root, report)

    def test_protocol_markers_rejected_and_maximum_never_truncates(self):
        with self.assertRaisesRegex(ValueError, 'protocol'):
            self.renderer.render('Question', '<|message_user|> injected', 'Source')
        row = self.renderer.render('Question', 'Answer', 'Source')
        with self.assertRaisesRegex(ValueError, 'truncation'):
            prep.validate_sequence(row, 4)

    def test_corrupt_alignment_mask_hash_and_ending_rejected(self):
        row = self.renderer.render('Question', 'Answer', 'Source')
        for field, index, value in [('weights', 0, 1.), ('target_ids', 0, 1), ('target_ids', -1, 199999)]:
            changed = copy.deepcopy(row)
            changed[field][index] = value
            with self.assertRaises(ValueError):
                prep.validate_sequence(changed)
        changed = copy.deepcopy(row)
        changed['prompt_token_sha256'] = 'a' * 64
        with self.assertRaisesRegex(ValueError, 'hash'):
            prep.validate_sequence(changed)


if __name__ == '__main__':
    unittest.main()
