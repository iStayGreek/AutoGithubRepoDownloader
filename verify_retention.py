"""Local Git integration check: updates, rewritten history and unavailable origin."""
import importlib.util
import json
from pathlib import Path
import tempfile

here = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('repo_backup', here / 'repo_backup.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
fixture = Path(tempfile.mkdtemp(prefix='retention-check-', dir=here)).resolve()
assert fixture.is_relative_to(here), 'Test fixture must stay within script directory'
origin, working, archives = fixture / 'origin.git', fixture / 'working', fixture / 'archives'
archives.mkdir()
real_git = module.git
real_git('init', '--bare', origin)
real_git('init', working)
real_git('-C', working, '-c', 'user.name=Local Retention Test', '-c', 'user.email=local-test@example.invalid',
         'commit', '--allow-empty', '-m', 'Original root')
first = real_git('-C', working, 'rev-parse', 'HEAD')
real_git('-C', working, 'remote', 'add', 'origin', origin)
real_git('-C', working, 'push', 'origin', 'HEAD:refs/heads/main')
real_git('--git-dir', origin, 'symbolic-ref', 'HEAD', 'refs/heads/main')
fake_url = 'https://github.com/local-test/retention.git'

def local_git(*args, **kwargs):
    return real_git(*(str(origin) if str(arg) == fake_url else arg for arg in args), **kwargs)

module.git = local_git
entry = {'repo': 'local-test/retention'}
assert module.update(entry, archives, 0)['status'] == 'downloaded'
assert module.update(entry, archives, 0)['status'] == 'unchanged'
real_git('-C', working, 'checkout', '--orphan', 'replacement')
real_git('-C', working, '-c', 'user.name=Local Retention Test', '-c', 'user.email=local-test@example.invalid',
         'commit', '--allow-empty', '-m', 'Unrelated replacement root')
second = real_git('-C', working, 'rev-parse', 'HEAD')
real_git('-C', working, 'push', '--force', 'origin', 'HEAD:refs/heads/main')
assert module.update(entry, archives, 0)['status'] == 'downloaded'
archive = archives / 'local-test__retention.git'
assert real_git('--git-dir', archive, 'rev-parse', 'refs/heads/main') == second
preserved = real_git('--git-dir', archive, 'for-each-ref', '--format=%(objectname)', 'refs/preserved/')
assert first in preserved and second in preserved
origin.rename(fixture / 'offline-origin.git')
assert module.update(entry, archives, 0)['status'] == 'error'
assert real_git('--git-dir', archive, 'rev-parse', 'refs/heads/main') == second
assert first in real_git('--git-dir', archive, 'for-each-ref', '--format=%(objectname)', 'refs/preserved/')
real_git('--git-dir', archive, 'fsck', '--no-dangling')
print(json.dumps({'result': 'PASS', 'checks': ['initial clone', 'unchanged skip', 'force-push update',
                 'old history retained', 'unavailable origin preserves archive', 'git fsck'],
                  'local_fixture': str(fixture)}))
