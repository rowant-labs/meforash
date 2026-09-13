"""Offline receipt/identity checks; never import Modal or touch a provider."""
import ast
import json
from pathlib import Path
import unittest
from typing import Any


SOURCE = Path(__file__).resolve().parents[1] / 'tools/modal_adapter_loader_pilot_v1.py'
NAMES = {'_model_manifest_bytes', '_final_text', '_final_receipt'}
namespace = {'json': json, 'Any': Any, 'MODEL_ID': 'openai/gpt-oss-20b',
             'MODEL_REVISION': 'test-revision'}
tree = ast.parse(SOURCE.read_text())
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)
                             and n.name in NAMES], type_ignores=[]), str(SOURCE), 'exec'), namespace)


class LoaderReceiptTests(unittest.TestCase):
    def response(self, model='adapter', finish='stop', content='Final answer'):
        return {'model': model, 'usage': {'total_tokens': 5}, 'choices': [{
            'finish_reason': finish,
            'message': {'content': content, 'reasoning_content': 'private reasoning'},
            'logprobs': {'content': [{'token': 'private token', 'logprob': -0.1}]}}]}

    def test_model_manifest_preserves_previously_pinned_schema(self):
        raw = namespace['_model_manifest_bytes']([
            {'path': 'b', 'bytes': 10, 'size': 10, 'sha256': 'abc'},
            {'path': 'a', 'bytes': 12, 'size': 12, 'sha256': 'def'}])
        decoded = json.loads(raw)
        self.assertEqual(decoded['files'], [
            {'path': 'a', 'size': 12, 'sha256': 'def'},
            {'path': 'b', 'size': 10, 'sha256': 'abc'}])
        self.assertNotIn('bytes', raw.decode())

    def test_receipt_contains_no_reasoning_or_raw_tokens(self):
        receipt = namespace['_final_receipt'](self.response(), 'adapter')
        self.assertEqual(receipt['final_content'], 'Final answer')
        self.assertNotIn('private', json.dumps(receipt))

    def test_response_identity_is_not_inferred_from_request(self):
        with self.assertRaises(RuntimeError):
            namespace['_final_receipt'](self.response(model='base'), 'adapter')

    def test_partial_or_empty_answer_does_not_pass(self):
        for response in [self.response(finish='length'), self.response(content='')]:
            with self.assertRaises(RuntimeError):
                namespace['_final_receipt'](response, 'adapter')


if __name__ == '__main__':
    unittest.main()
