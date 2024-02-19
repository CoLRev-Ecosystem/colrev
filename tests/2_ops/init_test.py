#!/usr/bin/env python
"""Tests of the CoLRev init operation"""
import os
from pathlib import Path

import pytest

import colrev.exceptions as colrev_exceptions
import colrev.review_manager


def test_repo_init_errors(tmp_path, helpers) -> None:  # type: ignore
    """Test repo init error (non-empty dir)"""

    review_manager = colrev.review_manager.ReviewManager(
        path_str=str(tmp_path), force_mode=True
    )
    review_manager.settings = colrev.settings.load_settings(
        settings_path=helpers.test_data_path.parents[1]
        / Path("colrev/template/init/settings.json")
    )

    with pytest.raises(colrev_exceptions.RepoInitError):
        colrev.review_manager.get_init_operation(
            review_type="literature_review",
            example=True,
            local_pdf_collection=True,
            target_path=tmp_path,
            light=True,
        )

    with pytest.raises(colrev_exceptions.ParameterError):
        colrev.review_manager.get_init_operation(
            review_type="misspelled_review", target_path=tmp_path
        )

    colrev.review_manager.get_init_operation(
        review_type="literature_review",
        example=True,
        target_path=tmp_path,
        light=True,
    )


def test_non_empty_dir_error_init(tmp_path) -> None:  # type: ignore
    """Test repo init error (non-empty dir)"""
    # A .report.log file that should be removed
    (tmp_path / colrev.review_manager.ReviewManager.REPORT_RELATIVE).write_text(
        "test", encoding="utf-8"
    )
    (tmp_path / Path("test.txt")).write_text("test", encoding="utf-8")
    with pytest.raises(colrev_exceptions.NonEmptyDirectoryError):
        colrev.review_manager.get_init_operation(
            review_type="literature_review",
            example=False,
            target_path=tmp_path,
            light=True,
        )
    Path("test.txt").unlink()


def local_pdf_collection(helpers, tmp_path_factory):  # type: ignore
    """Test the local_pdf_collection setup"""
    test_repo_dir = tmp_path_factory.mktemp("test_repo_local_pdf_collection")  # type: ignore
    os.chdir(test_repo_dir)
    review_manager = colrev.review_manager.ReviewManager(
        path_str=str(test_repo_dir), force_mode=True
    )
    review_manager.settings = colrev.settings.load_settings(
        settings_path=helpers.test_data_path.parents[1]
        / Path("colrev/template/init/settings.json")
    )

    review_manager = colrev.review_manager.get_init_operation(
        review_type="curated_masterdata",
        example=False,
        local_pdf_collection=True,
        light=True,
    )
