import json
from pathlib import Path
import tempfile
import unittest

from repo_backup import load_config


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'repositories.json'

    def load(self, repos, **options):
        self.path.write_text(json.dumps(dict(repositories=repos, **options)), encoding='utf-8')
        return load_config(self.path)

    def test_paths_relative_to_config(self):
        config = self.load([{'repo': 'octocat/Hello-World', 'seed': 'checkout'}])
        self.assertEqual(Path(config['archive_directory']), self.path.parent / 'archives')
        self.assertEqual(Path(config['repositories'][0]['seed']), self.path.parent / 'checkout')

    def test_invalid_names_and_duplicates(self):
        for names in [[], ['../escape'], ['owner/../escape'], ['-owner/repo'],
                      ['owner/repo', 'OWNER/REPO']]:
            with self.subTest(names=names), self.assertRaises(ValueError):
                self.load([{'repo': name} for name in names])

    def test_invalid_numbers(self):
        for option in [{'interval_minutes': 0}, {'minimum_free_gib': -1},
                       {'interval_minutes': True}, {'interval_minutes': float('nan')}]:
            with self.subTest(option=option), self.assertRaises(ValueError):
                self.load([{'repo': 'owner/repo'}], **option)


if __name__ == '__main__':
    unittest.main()
