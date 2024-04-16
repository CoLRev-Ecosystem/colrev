#!/usr/bin/env python
"""Tests of the CoLRev status operation"""
import colrev.review_manager


def test_get_analytics(  # type: ignore
    base_repo_review_manager: colrev.review_manager.ReviewManager, helpers
) -> None:
    """Test the prescreen operation"""

    helpers.reset_commit(base_repo_review_manager, commit="dedupe_commit")

    status_operation = base_repo_review_manager.get_status_operation()
    ret = status_operation.get_analytics()

    for details in ret.values():
        details.pop("commit_id", None)
        details.pop("committed_date", None)

    assert ret == {
        5: {
            "atomic_steps": 9,
            "completed_atomic_steps": 4,
            "commit_author": "script: -s test_records.bib",
            "commit_message": "Merge duplicate records",
            "search": 1,
            "included": 0,
        },
        4: {
            "atomic_steps": 9,
            "completed_atomic_steps": 3,
            "commit_author": "script: -s test_records.bib",
            "commit_message": "Prepare records (prep)",
            "search": 1,
            "included": 0,
        },
        3: {
            "atomic_steps": 9,
            "completed_atomic_steps": 2,
            "commit_author": "script: -s test_records.bib",
            "commit_message": "Load test_records.bib",
            "search": 1,
            "included": 0,
        },
        2: {
            "atomic_steps": 9,
            "completed_atomic_steps": 1,
            "commit_author": "script:",
            "commit_message": "Add new search sources",
            "search": 1,
            "included": 0,
        },
        1: {
            "atomic_steps": 0,
            "completed_atomic_steps": 0,
            "commit_author": "Tester Name",
            "commit_message": "Initial commit",
            "search": 0,
            "included": 0,
        },
    }


def test_status_stats(  # type: ignore
    base_repo_review_manager: colrev.review_manager.ReviewManager, helpers
) -> None:
    colrev.process.operation.CheckOperation(base_repo_review_manager)

    records = base_repo_review_manager.dataset.load_records_dict()
    status_stats = base_repo_review_manager.get_status_stats(records=records)
    print(status_stats)
    assert status_stats.atomic_steps == 9


def test_get_review_status_report(  # type: ignore
    base_repo_review_manager: colrev.review_manager.ReviewManager, helpers
) -> None:
    """Test the prescreen operation"""

    helpers.reset_commit(base_repo_review_manager, commit="dedupe_commit")

    status_operation = base_repo_review_manager.get_status_operation()
    ret = status_operation.get_review_status_report(colors=True)
    print(ret)
    assert (
        ret
        == """Status
    init
    retrieve          1 retrieved     [only 0 quality-curated]
    prescreen         0 included      1 to prescreen
    pdfs              0 retrieved
    screen            0 included
    data              0 synthesized"""
    )
