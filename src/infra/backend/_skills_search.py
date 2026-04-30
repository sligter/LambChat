"""
Search helpers for SkillsStoreBackend.

Contains grep and glob utility methods used by the backend.
"""

import fnmatch

from src.infra.backend.protocol_compat import FileInfo, GrepMatch
from src.infra.logging import get_logger

logger = get_logger(__name__)


async def grep_single_skill(
    pattern: str,
    glob_pattern: str | None,
    skill_name: str,
    storage,
    file_paths: list[str],
    user_id: str,
    is_skill_visible_fn,
) -> list[GrepMatch]:
    """在单个 skill 的指定文件中搜索"""
    if not is_skill_visible_fn(skill_name):
        return []

    if not file_paths:
        return []

    if glob_pattern:
        file_paths = [
            p
            for p in file_paths
            if fnmatch.fnmatch(p, glob_pattern) or fnmatch.fnmatch(p.split("/")[-1], glob_pattern)
        ]

    if not file_paths:
        return []

    files_map = await storage.batch_get_skill_files([(skill_name, user_id)])
    files = files_map.get((skill_name, user_id), {})

    matches: list[GrepMatch] = []
    for fp in file_paths:
        content = files.get(fp)
        if content is None:
            continue
        for i, line in enumerate(content.split("\n"), start=1):
            if pattern in line:
                matches.append(
                    GrepMatch(
                        path=f"/{skill_name}/{fp}",
                        line=i,
                        text=line[:2000],
                    )
                )

    return matches


def grep_across_skills(
    pattern: str,
    glob_pattern: str | None,
    all_files: dict[tuple[str, str], dict[str, str]],
) -> list[GrepMatch]:
    """在多个 skill 中搜索"""
    matches: list[GrepMatch] = []
    for (skill_name, _user_id), files in all_files.items():
        for fp, content in files.items():
            if glob_pattern and not (
                fnmatch.fnmatch(fp, glob_pattern)
                or fnmatch.fnmatch(fp.split("/")[-1], glob_pattern)
            ):
                continue
            for i, line in enumerate(content.split("\n"), start=1):
                if pattern in line:
                    matches.append(
                        GrepMatch(
                            path=f"/{skill_name}/{fp}",
                            line=i,
                            text=line[:2000],
                        )
                    )
    return matches


def build_file_list_from_paths(skill_name: str, prefix: str, paths: list[str]) -> list[FileInfo]:
    """构建 skill 目录的文件列表（仅路径，无内容大小）"""
    entries: list[FileInfo] = []
    seen_dirs: set[str] = set()

    prefix_slash = f"{prefix}/" if prefix else ""

    for file_path in paths:
        if not file_path.startswith(prefix_slash):
            continue

        relative = file_path[len(prefix_slash) :]
        slash_idx = relative.find("/")
        if slash_idx >= 0:
            dir_name = relative[:slash_idx]
            if dir_name not in seen_dirs:
                seen_dirs.add(dir_name)
                entries.append(
                    FileInfo(
                        path=f"/{skill_name}/{prefix_slash}{dir_name}/",
                        is_dir=True,
                    )
                )
        else:
            entries.append(
                FileInfo(
                    path=f"/{skill_name}/{file_path}",
                    is_dir=False,
                )
            )

    return entries


def glob_files_from_paths(
    skill_name: str, prefix: str, pattern: str, paths: list[str]
) -> list[FileInfo]:
    """在 skill 文件路径中按 glob 模式匹配（无内容大小）"""
    prefix_slash = f"{prefix}/" if prefix else ""
    entries: list[FileInfo] = []

    for file_path in paths:
        if not file_path.startswith(prefix_slash):
            continue

        relative = file_path[len(prefix_slash) :]
        basename = relative.rsplit("/", 1)[-1] if "/" in relative else relative

        if fnmatch.fnmatch(basename, pattern):
            entries.append(
                FileInfo(
                    path=f"/{skill_name}/{file_path}",
                    is_dir=False,
                )
            )

    return entries
