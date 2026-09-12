"""Read naturally ordered image metadata from an already resolved directory."""

import os
from dataclasses import dataclass

from natsort import natsorted

from utils.file_utils import is_image_file
from utils.path_utils import join_path


@dataclass(frozen=True)
class BookImageFile:
    name: str
    mtime_ns: int


class ImageDirectoryMissingError(FileNotFoundError):
    """The requested directory was absent before enumeration."""


class ImageDirectoryNotDirectoryError(NotADirectoryError):
    """The requested path existed but was not a directory."""


def list_book_image_files(directory: str) -> list[BookImageFile]:
    """Caller must validate and resolve the path within the selected source root."""
    if not os.path.exists(directory):
        raise ImageDirectoryMissingError(directory)
    if not os.path.isdir(directory):
        raise ImageDirectoryNotDirectoryError(directory)

    images = natsorted(name for name in os.listdir(directory) if is_image_file(name))
    # Do not translate later I/O failures into a directory-not-found result.
    return [BookImageFile(name, os.stat(join_path(directory, name)).st_mtime_ns) for name in images]
