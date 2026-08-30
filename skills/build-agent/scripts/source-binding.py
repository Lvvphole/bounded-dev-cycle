#!/usr/bin/env python3
"""Compute the canonical repository source binding for a PLAN_READY artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path, PurePosixPath

GIT_KEEP_ENV = (
    'PATH',
    'HOME',
    'SYSTEMROOT',
    'GIT_EXEC_PATH',
    'GIT_SSL_CAINFO',
    'GIT_SSL_CAPATH',
)

GIT_PINNED_CONFIG = (
    'core.abbrev=40',
    'core.autocrlf=false',
    'core.quotePath=true',
    'diff.algorithm=myers',
    'diff.context=3',
    'diff.ignoreSubmodules=none',
    'diff.indentHeuristic=true',
    'diff.mnemonicPrefix=false',
    'diff.noprefix=false',
    'diff.relative=false',
    'diff.suppressBlankEmpty=false',
)


def repo_relative_path(value: str, label: str) -> str:
    path = PurePosixPath(value.replace('\\', '/'))
    canonical = path.as_posix()
    if (
        not value
        or path.is_absolute()
        or '..' in path.parts
        or path == PurePosixPath('.')
        or re.match(r'^[A-Za-z]:/', canonical)
        or value.replace('\\', '/') != canonical
    ):
        raise ValueError(f'{label} must be a canonical repository-relative path without ..')
    return canonical


def git_environment(neutral_file: Path) -> dict[str, str]:
    """Drop ambient configuration so only pinned values and repository data apply."""
    env = {name: os.environ[name] for name in GIT_KEEP_ENV if name in os.environ}
    env['GIT_CONFIG_GLOBAL'] = str(neutral_file)
    env['GIT_CONFIG_SYSTEM'] = str(neutral_file)
    env['GIT_CONFIG_NOSYSTEM'] = '1'
    env['GIT_ATTR_NOSYSTEM'] = '1'
    env['LC_ALL'] = 'C'
    env['TZ'] = 'UTC'
    return env


def git(repo: Path, neutral_file: Path, *args: str) -> bytes:
    pins: list[str] = []
    for setting in (*GIT_PINNED_CONFIG, f'diff.orderFile={neutral_file}'):
        pins.extend(['-c', setting])
    result = subprocess.run(
        ['git', *pins, '-C', str(repo), *args],
        check=True,
        env=git_environment(neutral_file),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: object) -> bytes:
    # ensure_ascii=True: filesystem paths reach here via surrogateescape decoding and
    # may contain lone surrogates that are not valid UTF-8. \\uXXXX-escaping keeps the
    # output distinguishable per distinct byte sequence and always ASCII-encodable.
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode('ascii')


def diff_bytes(repo: Path, neutral_file: Path, excluded: str, *, staged: bool) -> bytes:
    args = ['diff']
    if staged:
        args.append('--cached')
    args.extend([
        '--binary',
        '--full-index',
        '--no-ext-diff',
        '--no-textconv',
        '--no-renames',
        '--no-color',
        '--src-prefix=a/',
        '--dst-prefix=b/',
        '--',
        '.',
        f':(exclude){excluded}',
    ])
    return git(repo, neutral_file, *args)


def nested_repo_sha256(root: Path) -> str:
    """Bind an untracked nested repository by its worktree content, not its history."""
    entries: list[dict[str, str | int]] = []
    pending = [root]
    while pending:
        current = pending.pop()
        for item in os.scandir(current):
            if item.name == '.git':
                continue
            path = Path(item.path)
            relative = path.relative_to(root).as_posix()
            if path.is_dir() and not path.is_symlink():
                pending.append(path)
                continue
            entries.append(worktree_entry(path, relative))
    entries.sort(key=lambda entry: os.fsencode(str(entry['path'])))
    return sha256(canonical_json(entries))


def worktree_entry(path: Path, relative: str) -> dict[str, str | int]:
    info = path.lstat()
    mode = stat.S_IMODE(info.st_mode)
    if stat.S_ISLNK(info.st_mode):
        content = os.fsencode(os.readlink(path))
        return {'path': relative, 'kind': 'symlink', 'mode': mode, 'sha256': sha256(content)}
    if stat.S_ISREG(info.st_mode):
        return {'path': relative, 'kind': 'file', 'mode': mode, 'sha256': sha256(path.read_bytes())}
    if stat.S_ISDIR(info.st_mode):
        # Git reports an untracked directory only when it refuses to descend into it,
        # which means a nested repository.
        return {'path': relative, 'kind': 'nested-repo', 'mode': mode, 'sha256': nested_repo_sha256(path)}
    raise ValueError(f'unsupported untracked file type: {relative}')


def dirty_submodule_manifest(repo: Path, neutral_file: Path) -> bytes:
    """Hash the worktree content of every tracked submodule with uncommitted changes.

    A top-level ``git diff`` only ever records a dirty submodule as its checked-out
    commit with a generic ``-dirty`` suffix, so two different uncommitted submodule
    states are indistinguishable to ``diff_bytes``. Any submodule with modified
    tracked content (``m == 'M'``) or untracked content (``u == 'U'``) is hashed here
    by worktree content, the same way an untracked nested repository is hashed.
    """
    raw = git(
        repo, neutral_file,
        'status', '--porcelain=v2', '-z',
        '--ignore-submodules=none', '--untracked-files=no',
        '--', '.',
    )
    records = raw.split(b'\0')
    entries: list[dict[str, str | int]] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        text = record.decode('utf-8', 'surrogateescape')
        if text.startswith('2 '):
            # Renamed/copied entries carry one extra NUL-separated origPath token.
            index += 1
        if not (text.startswith('1 ') or text.startswith('2 ')):
            continue
        fields = text.split(' ', 8)
        if len(fields) < 9:
            continue
        sub_field, relative = fields[2], fields[8]
        if len(sub_field) != 4 or sub_field[0] != 'S':
            continue
        _commit_flag, tracked_flag, untracked_flag = sub_field[1], sub_field[2], sub_field[3]
        if tracked_flag != 'M' and untracked_flag != 'U':
            continue
        entries.append({
            'path': relative,
            'kind': 'dirty-submodule',
            'sha256': nested_repo_sha256(repo / relative),
        })
    entries.sort(key=lambda entry: str(entry['path']).encode('utf-8', 'surrogateescape'))
    return canonical_json(entries)


def untracked_manifest(repo: Path, neutral_file: Path, excluded: str) -> bytes:
    raw = git(repo, neutral_file, 'ls-files', '--others', '--exclude-standard', '-z')
    excluded_bytes = os.fsencode(excluded)
    paths = sorted(path for path in raw.split(b'\0') if path and path != excluded_bytes)
    entries = []
    for path_bytes in paths:
        relative = os.fsdecode(path_bytes).rstrip('/').replace(os.sep, '/')
        entries.append(worktree_entry(repo / relative, relative))
    return canonical_json(entries)


def compute(repo: Path, excluded_plan_path: str) -> dict[str, str]:
    excluded = repo_relative_path(excluded_plan_path, 'excluded plan path')
    with tempfile.TemporaryDirectory() as scratch:
        neutral_file = Path(scratch) / 'neutral'
        neutral_file.write_bytes(b'')
        top_level = git(repo, neutral_file, 'rev-parse', '--show-toplevel').strip()
        root = Path(os.fsdecode(top_level)).resolve()
        return {
            'commit': os.fsdecode(git(root, neutral_file, 'rev-parse', 'HEAD').strip()),
            'staged_diff_sha256': sha256(diff_bytes(root, neutral_file, excluded, staged=True)),
            'unstaged_diff_sha256': sha256(diff_bytes(root, neutral_file, excluded, staged=False)),
            'untracked_manifest_sha256': sha256(untracked_manifest(root, neutral_file, excluded)),
            'dirty_submodule_manifest_sha256': sha256(dirty_submodule_manifest(root, neutral_file)),
            'excluded_plan_path': excluded,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default='.', help='path inside the Git repository')
    parser.add_argument('--exclude-plan-path', required=True)
    args = parser.parse_args()
    try:
        binding = compute(Path(args.repo), args.exclude_plan_path)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(binding, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
