"""Keep independent, non-pruning Git archives. Never run downloaded project code."""
import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
LOG = logging.getLogger('repository-backups')


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def write_json(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def git(*args, timeout=900):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='Never')
    executable = shutil.which('git')
    if not executable:
        raise RuntimeError('Git must be installed and available on PATH')
    command = [executable,
               '-c', 'credential.helper=', '-c', 'core.hooksPath=' + str(HERE / 'empty-hooks'),
               '-c', 'gc.auto=0', '-c', 'maintenance.auto=false', *map(str, args)]
    result = subprocess.run(command, capture_output=True, text=True, errors='replace',
                            env=env, timeout=timeout, creationflags=CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip()[-1200:])
    return result.stdout.strip()


def refs(archive):
    return git('--git-dir', archive, 'for-each-ref', '--format=%(refname) %(objectname)',
               'refs/heads/', 'refs/tags/')


def preserve(archive):
    """Durable refs retain old commits and tags even after upstream force pushes."""
    current = refs(archive)
    if not current:
        return
    identity = hashlib.sha256(current.encode()).hexdigest()[:16]
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')
    for line in current.splitlines():
        ref, oid = line.split(' ', 1)
        git('--git-dir', archive, 'update-ref',
            'refs/preserved/' + stamp + '-' + identity + '/' + ref[5:], oid)


def configure(archive, url):
    for key, value in [('remote.origin.url', url), ('remote.origin.mirror', 'false'),
                       ('fetch.prune', 'false'), ('fetch.pruneTags', 'false'),
                       ('gc.auto', '0'), ('gc.pruneExpire', 'never'), ('maintenance.auto', 'false')]:
        git('--git-dir', archive, 'config', key, value)


def update(entry, root, minimum_free):
    repo = entry['repo']
    url = 'https://github.com/' + repo + '.git'
    archive = root / (repo.replace('/', '__') + '.git')
    state_path = root / (repo.replace('/', '__') + '.status.json')
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    state.update(repo=repo, url=url, archive=str(archive), checked_at=utc(), status='checking')
    try:
        # Rescue a supplied existing checkout before trying an unavailable upstream.
        seed = entry.get('seed')
        if not archive.exists() and seed and Path(seed).is_dir():
            if shutil.disk_usage(root).free < minimum_free:
                raise RuntimeError('Less than configured minimum free space; seed deferred')
            git('-c', 'safe.directory=' + seed, 'clone', '--bare', '--no-hardlinks', seed, archive)
            configure(archive, url)
            preserve(archive)
            state['seeded_at'] = utc()
            LOG.info('%s: preserved existing local checkout', repo)
        remote = git('ls-remote', '--heads', '--tags', url, timeout=90)
        signature = hashlib.sha256(remote.encode()).hexdigest()
        if archive.exists() and state.get('remote_signature') == signature:
            state.update(status='unchanged', last_success=utc())
        else:
            if shutil.disk_usage(root).free < minimum_free:
                raise RuntimeError('Less than configured minimum free space; download deferred')
            if not archive.exists():
                # Only bare repositories created by this script live here. Clone
                # failure leaves its own staging folder, never deletes older data.
                staging = root / (archive.name + '.incoming-' + str(time.time_ns()))
                git('clone', '--bare', '--no-hardlinks', url, staging, timeout=3600)
                configure(staging, url)
                staging.rename(archive)
            else:
                configure(archive, url)
                preserve(archive)
                git('--git-dir', archive, 'fetch', '--no-prune', '--no-auto-maintenance',
                    '--force', 'origin', '+refs/heads/*:refs/heads/*',
                    '+refs/tags/*:refs/tags/*', timeout=3600)
            preserve(archive)
            state.update(status='downloaded', remote_signature=signature,
                         last_success=utc(), refs=refs(archive).splitlines())
            LOG.info('%s: latest branches/tags downloaded', repo)
        state.pop('error', None)
    except Exception as exc:
        state.update(status='error', error=str(exc))
        # Repeated upstream disappearance does not remove the local archive.
        LOG.warning('%s: %s', repo, str(exc))
    write_json(state_path, state)
    return state


def load_config(path):
    path = Path(path).resolve()
    config = json.loads(path.read_text(encoding='utf-8-sig'))
    entries = config['repositories']
    if not isinstance(entries, list) or not entries:
        raise ValueError('Configure at least one repository')
    names = [entry['repo'] for entry in entries]
    pattern = r'[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_][A-Za-z0-9_.-]*'
    if (not all(isinstance(name, str) and re.fullmatch(pattern, name) for name in names)
            or len({name.lower() for name in names}) != len(names)):
        raise ValueError('Repository IDs must be unique GitHub owner/name pairs')
    for field, default, minimum in [('interval_minutes', 30, 1), ('minimum_free_gib', 5, 0)]:
        value = config.get(field, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not minimum <= value < float('inf'):
            raise ValueError(field + ' must be a finite number >= ' + str(minimum))
        config[field] = value
    root = Path(config.get('archive_directory', 'archives')).expanduser()
    config['archive_directory'] = str((path.parent / root).resolve())
    for entry in entries:
        if entry.get('seed'):
            entry['seed'] = str((path.parent / Path(entry['seed']).expanduser()).resolve())
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true', help='One pass instead of continuous 30-minute checks')
    parser.add_argument('--repo', help='Limit this invocation to one configured owner/repository')
    parser.add_argument('--validate', action='store_true', help='Validate configuration without downloading')
    parser.add_argument('--config', type=Path, default=HERE / 'repositories.json', help='JSON configuration file')
    args = parser.parse_args()
    config = load_config(args.config)
    entries = config['repositories']
    if args.repo:
        entries = [entry for entry in entries if entry['repo'] == args.repo]
        if not entries:
            raise ValueError('Requested repository is not configured')
    root = Path(config['archive_directory']).resolve()
    root.mkdir(parents=True, exist_ok=True)
    (HERE / 'empty-hooks').mkdir(exist_ok=True)
    if args.validate:
        print(json.dumps({'repositories': len(entries), 'interval_minutes': config['interval_minutes'],
                          'archive_directory': str(root), 'git': git('--version')}))
        return 0
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[RotatingFileHandler(root / 'repo-backup.log', maxBytes=5_000_000,
                                                      backupCount=5, encoding='utf-8')])
    # A byte-range lock prevents duplicate workers, including manual --once runs.
    lock = (root / 'worker.lock').open('a+b')
    lock.seek(0)
    if os.name == 'nt':
        import msvcrt
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            LOG.info('Another repository backup worker is already active')
            return 0
    else:
        import fcntl
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            LOG.info('Another repository backup worker is already active')
            return 0
    write_json(root / 'worker.json', {'pid': os.getpid(), 'started_at': utc(), 'interval_minutes': config['interval_minutes']})
    minimum_free = config['minimum_free_gib'] * 1024**3
    interval = max(60, int(config['interval_minutes'] * 60))
    LOG.info('Worker started, %d repositories, every %d seconds', len(entries), interval)
    while True:
        started = time.monotonic()
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            pending = [pool.submit(update, entry, root, minimum_free) for entry in entries]
            for future in concurrent.futures.as_completed(pending):
                results.append(future.result())
                write_json(root / 'summary.json', {'updated_at': utc(), 'complete': False,
                           'expected_repositories': len(entries), 'repositories': results})
        write_json(root / 'summary.json', {'updated_at': utc(), 'complete': True,
                   'expected_repositories': len(entries), 'repositories': results})
        LOG.info('Pass complete: %d successful, %d errors',
                 sum(x['status'] != 'error' for x in results), sum(x['status'] == 'error' for x in results))
        if args.once:
            print(json.dumps({'checked': len(results), 'errors': sum(x['status'] == 'error' for x in results)}))
            return 1 if any(x['status'] == 'error' for x in results) else 0
        time.sleep(max(15, interval - (time.monotonic() - started)))


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        LOG.exception('Repository backup worker stopped unexpectedly')
        raise
