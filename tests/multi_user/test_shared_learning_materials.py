from __future__ import annotations

from deeptutor.book.context import build_book_context
from deeptutor.book.models import (
    Block,
    BlockStatus,
    BlockType,
    Book,
    BookStatus,
    Chapter,
    ContentType,
    Page,
    PageStatus,
    Progress,
    Spine,
)
from deeptutor.multi_user import book_access, notebook_access
from deeptutor.multi_user.book_access import (
    list_visible_books,
    resolve_book_for_read,
    resolve_book_for_write,
)
from deeptutor.multi_user.notebook_access import (
    get_records_by_references_for_current_user,
    list_visible_notebooks,
    resolve_notebook_for_read,
    resolve_notebook_for_write,
)


def _seed_admin_book(book_id: str) -> None:
    engine = book_access.admin_book_engine()
    book = Book(
        id=book_id,
        title="Shared Fractions",
        description="Common fifth-grade fraction notes.",
        status=BookStatus.READY,
        page_count=1,
        chapter_count=1,
    )
    spine = Spine(
        book_id=book_id,
        chapters=[
            Chapter(
                id="ch_fraction",
                title="Fraction Basics",
                content_type=ContentType.CONCEPT,
                page_ids=["pg_fraction"],
                order=1,
            )
        ],
    )
    page = Page(
        id="pg_fraction",
        book_id=book_id,
        chapter_id="ch_fraction",
        title="Understanding Numerators",
        content_type=ContentType.CONCEPT,
        status=PageStatus.READY,
        order=1,
        blocks=[
            Block(
                id="blk_numerator",
                type=BlockType.TEXT,
                status=BlockStatus.READY,
                title="Numerator",
                payload={"markdown": "A numerator counts selected equal parts."},
            )
        ],
    )
    engine.storage.save_book(book)
    engine.storage.save_spine(spine)
    engine.storage.save_page(page)
    engine.storage.save_progress(
        Progress(
            book_id=book_id,
            current_page_id="pg_fraction",
            visited_page_ids=["pg_fraction"],
            score=99,
        )
    )


def test_user_can_read_admin_notebooks_and_copy_before_writing(
    mu_isolated_root,
    as_user,
) -> None:
    with as_user("u_admin", role="admin", username="admin"):
        manager = notebook_access.admin_notebook_manager()
        notebook = manager.create_notebook(
            name="Shared Math Notes",
            description="Common admin notes",
        )
        saved = manager.add_record(
            notebook_ids=[notebook["id"]],
            record_type="chat",
            title="Fraction discussion",
            summary="Fractions compare equal parts.",
            user_query="Explain fractions",
            output="Fractions represent equal parts of a whole.",
        )

    with as_user("u_child", username="child"):
        visible = list_visible_notebooks()
        shared = next(item for item in visible if item["id"] == notebook["id"])
        assert shared["source"] == "admin"
        assert shared["read_only"] is True

        resolved = resolve_notebook_for_read(notebook["id"])
        assert resolved.source == "admin"
        assert resolved.read_only is True

        records = get_records_by_references_for_current_user(
            [
                {
                    "notebook_id": notebook["id"],
                    "record_ids": [saved["record"]["id"]],
                }
            ]
        )
        assert len(records) == 1
        assert records[0]["title"] == "Fraction discussion"
        assert records[0]["source"] == "admin"

        writable = resolve_notebook_for_write(notebook["id"], copy_public=True)
        assert writable.source == "user"
        assert writable.read_only is False
        assert writable.manager.get_notebook(notebook["id"]) is not None

        admin_copy = notebook_access.admin_notebook_manager().get_notebook(notebook["id"])
        assert admin_copy is not None
        assert admin_copy["records"][0]["title"] == "Fraction discussion"


def test_user_can_read_admin_books_and_copy_before_study_writes(
    mu_isolated_root,
    as_user,
) -> None:
    book_access._engines.clear()

    with as_user("u_admin", role="admin", username="admin"):
        _seed_admin_book("bk_shared_fraction")

    with as_user("u_child", username="child"):
        visible = list_visible_books()
        shared = next(item for item in visible if item["id"] == "bk_shared_fraction")
        assert shared["source"] == "admin"
        assert shared["read_only"] is True

        resolved = resolve_book_for_read("bk_shared_fraction")
        assert resolved.source == "admin"
        assert resolved.read_only is True

        context = build_book_context(
            [{"book_id": "bk_shared_fraction", "page_ids": ["pg_fraction"]}]
        )
        assert context.warnings == []
        assert "A numerator counts selected equal parts." in context.text

        writable = resolve_book_for_write("bk_shared_fraction", copy_public=True)
        assert writable.source == "user"
        assert writable.read_only is False
        assert writable.engine.load_book("bk_shared_fraction") is not None
        assert writable.engine.load_progress("bk_shared_fraction").visited_page_ids == []

        admin_progress = book_access.admin_book_engine().load_progress("bk_shared_fraction")
        assert admin_progress.visited_page_ids == ["pg_fraction"]
        assert admin_progress.score == 99
