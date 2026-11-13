# AutoGithubRepoDownloader

Automatically download and preserve the Git history of your favorite public GitHub repositories. Pick your own list, choose a folder, and let it check for updates every 30 minutes.

Runs locally and independently of Codex or any other chat app. Python standard library only; no pip packages required.

## Requirements

- Python 3.10 or newer, available as `python`.
- Git installed and available on PATH.
- Enough free storage for full Git histories. Large repositories can take a while on the first run.

## Quick start

Download this repository with **Code → Download ZIP** and extract it, or clone it:

```powershell
git clone https://github.com/iStayGreek/AutoGithubRepoDownloader.git
cd AutoGithubRepoDownloader
Copy-Item repositories.example.json repositories.json
```

Edit `repositories.json` with any text editor:

```json
{
  "archive_directory": "archives",
  "interval_minutes": 30,
  "minimum_free_gib": 5,
  "repositories": [
    { "repo": "octocat/Hello-World" },
    { "repo": "git/git" }
  ]
}
```

Use `owner/repository`, not a full URL. Paths are relative to the configuration file; absolute paths also work. The free-space threshold prevents starting another download below that amount, but an in-progress download can cross it.

Validate the configuration and try one pass:

```powershell
python repo_backup.py --validate
python repo_backup.py --once
```

For continuous checks in the current terminal:

```powershell
python repo_backup.py
```

Stop with Ctrl+C. Restart after editing the configuration; it is read at startup. A slow pass finishes before the next pass begins.

## Start automatically on Windows

From PowerShell in this folder:

```powershell
.\Install-Task.ps1
```

This starts a hidden worker immediately and at each Windows sign-in. It runs as your normal user, requires no administrator rights or stored password, and does not depend on Codex being open. The PC must be awake and you must be signed in. Keep this project folder in place after installation.

If Python isn't detected correctly:

```powershell
.\Install-Task.ps1 -PythonPath 'C:\Path\To\Python\python.exe'
```

Use `-ConfigPath` for a different configuration. Use `-TaskName` if you need a custom task name. The installer refuses to overwrite an existing task.

Pause or resume from PowerShell:

```powershell
Stop-ScheduledTask -TaskName 'GitHub Repository Archiver'
Start-ScheduledTask -TaskName 'GitHub Repository Archiver'
```

Remove automatic startup and stop the worker:

```powershell
.\Uninstall-Task.ps1
```

Archives and configuration are kept. If you used a custom task name, pass the same `-TaskName` to the uninstall script. If PowerShell blocks local scripts, use your usual trusted-script workflow; this project does not change your execution policy.

## What it preserves

- Independent bare Git repositories named `owner__repository.git`.
- All advertised branches and tags, including their reachable Git history.
- Previous branch/tag targets under `refs/preserved/` before updates, retaining history after force pushes or tag rewrites.
- Deleted upstream branches and tags: fetching never prunes them.
- Existing archives when GitHub is unavailable or a repository disappears.

It checks upstream references first and skips downloads if they have not changed. Two repositories can download at a time. A local lock prevents two workers from writing to the same archive folder.

Downloaded project code and Git hooks are not executed. Git settings are scoped to this script's commands and archives; global Git configuration is not changed. Authentication prompts and credential helpers are disabled, so this version targets public repositories.

**Scope:** Git source history only. Release downloads, Git LFS file contents, submodule repositories, issues, pull-request discussions, wikis and other GitHub metadata are not backed up. It cannot recover content that was already unavailable before your first successful download. Archives grow over time and are not automatically cleaned up. Interrupted initial clones may leave an `.incoming-*` directory for manual inspection.

## Status and troubleshooting

Inside the archive folder:

- `summary.json`: latest pass results, including a `complete` flag.
- `owner__repository.status.json`: each repo's last success or error.
- `repo-backup.log`: rotating activity/error log.
- `worker.json`: worker start information; a recorded PID alone does not prove it is still running.

An unavailable repo is logged and retried on later passes; its archive is kept. `--once` exits with code 1 if any repo fails, otherwise 0. Configuration errors stop the worker. Avoid running a manual pass while the background worker is active; the duplicate invocation exits without starting another pass.

Other options:

```powershell
python repo_backup.py --config another-list.json --once
python repo_backup.py --once --repo octocat/Hello-World
```

To import an existing local checkout before attempting GitHub, add an optional `"seed": "path/to/checkout"` field to that repo's entry. It is copied into an independent archive, leaving the checkout untouched.

## Use a saved archive

Create a normal working checkout:

```powershell
git clone archives/octocat__Hello-World.git restored-project
```

Inspect retained history:

```powershell
git --git-dir=archives/octocat__Hello-World.git for-each-ref refs/preserved/
```

Use a commit hash from that output with `git checkout` in a working checkout. Keep a separate copy of your archive folder if you need protection against disk failure.

## Development

```powershell
python -m unittest -v
python verify_retention.py
```

The integration check uses local Git repositories, tests force-push retention and upstream loss, and runs `git fsck`. Test fixtures are left in an ignored `retention-check-*` folder for inspection. CI runs these checks on Windows and Linux. The Python worker supports both; automatic startup scripts are Windows-only.

MIT licensed. Contributions welcome.
