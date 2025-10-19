from abc import ABC, abstractmethod
from typing import IO
from msgspec import UNSET, Struct, UnsetType
from io import BytesIO

from autocrud.resource_manager.core import ResourceManager
from autocrud.types import RevisionInfo
import mimetypes
import magic
from xxhash import xxh128


class Content(Struct, tag=True):
    data: bytes
    mime: str
    size: int
    hash: str | UnsetType = UNSET


class ContentPointer(Struct, tag=True):
    content_id: str
    content_hash: str | UnsetType = UNSET


class FileResource(Struct):
    filename: str
    content: ContentPointer | Content


class SymLink(Struct, tag=True):
    target_filename: str


class Dir(Struct, tag=True):
    pass


class FilesetResource(Struct):
    files: dict[str, ContentPointer | Content | SymLink | Dir]


PathStr = str


class IFileResourceManager(ResourceManager[FileResource], ABC):
    @abstractmethod
    def create_file(
        self,
        filename: str,
        file_obj: PathStr | bytes | IO[bytes] | None = None,
        mime: str | UnsetType = UNSET,
    ) -> RevisionInfo:
        """Create a file resource from a file object, bytes, or file path."""

    @abstractmethod
    def get_content(self, content_pointer: ContentPointer) -> Content:
        """Get content by content pointer."""


class FileResourceManager(IFileResourceManager):
    def __init__(self, *args, content_manager: ResourceManager[Content], **kwargs):
        super().__init__(*args, **kwargs)
        self.content_manager = content_manager
        self.large_file_threshold = 2048

    def _guess_content_type(self, filename: str, file_obj: IO[bytes]) -> str:
        mime, _ = mimetypes.guess_type(filename)
        if mime is not None:
            return mime
        try:
            mime = magic.from_buffer(file_obj.read(2048), mime=True)
            return mime
        except Exception:
            return "application/octet-stream"
        finally:
            file_obj.seek(0)

    def calc_content_id(self, file_obj: IO[bytes]) -> str:
        hasher = xxh128()
        file_obj.seek(0)
        while True:
            chunk = file_obj.read(8192)
            if not chunk:
                break
            hasher.update(chunk)
        file_obj.seek(0)
        return self.content_manager.resource_name + ":" + hasher.hexdigest()

    def _create_file(
        self,
        filename: str,
        file_obj: IO[bytes],
        mime: str | UnsetType = UNSET,
    ):
        if mime is UNSET:
            mime = self._guess_content_type(filename, file_obj)
        content = Content(
            data=file_obj.read(),
            mime=mime,
            size=file_obj.seek(0, 2),
        )
        if content.size > self.large_file_threshold:
            with self.content_manager.meta_provide(
                self.user, self.now, resource_id=self.calc_content_id(file_obj)
            ) as mgr:
                info = mgr.create(content)
            content = ContentPointer(
                content_id=info.resource_id,
                content_hash=content.hash,
            )
        r = FileResource(
            filename=filename,
            content=content,
        )
        return self.create(r)

    def create_file(
        self,
        filename: str,
        file_obj: PathStr | bytes | IO[bytes] | None = None,
        mime: str | UnsetType = UNSET,
    ) -> RevisionInfo:
        if file_obj is None:
            file_obj = PathStr(filename)
        if isinstance(file_obj, PathStr):
            with open(file_obj, "rb") as f:
                return self._create_file(filename, f, mime)
        elif isinstance(file_obj, bytes):
            with BytesIO(file_obj) as f:
                return self._create_file(filename, f, mime)
        else:
            return self._create_file(filename, file_obj, mime)

    def get_content(self, content_pointer: ContentPointer) -> Content:
        content_rev = self.content_manager.get(content_pointer.content_id)
        return content_rev.data
