#! /usr/bin/env python
"""CLI interface for manual preparation of PDFs"""
from __future__ import annotations

import os
import platform
import re
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import inquirer
import zope.interface
from dataclasses_jsonschema import JsonSchemaMixin

import colrev.env.package_manager
import colrev.exceptions as colrev_exceptions
import colrev.record
from colrev.constants import Colors
from colrev.constants import Fields

if TYPE_CHECKING:
    import colrev.ops.pdf_prep_man


# pylint: disable=too-few-public-methods


@zope.interface.implementer(
    colrev.env.package_manager.PDFPrepManPackageEndpointInterface
)
@dataclass
class CoLRevCLIPDFManPrep(JsonSchemaMixin):
    """Manually prepare PDFs based on a CLI (not yet implemented)"""

    settings_class = colrev.env.package_manager.DefaultSettings
    ci_supported: bool = False

    __to_skip: int = 0

    def __init__(
        self,
        *,
        pdf_prep_man_operation: colrev.ops.pdf_prep_man.PDFPrepMan,
        settings: dict,
    ) -> None:
        self.settings = self.settings_class.load_settings(data=settings)
        self.review_manager = pdf_prep_man_operation.review_manager

    def __update_metadata(
        self, *, record: colrev.record.Record
    ) -> colrev.record.Record:
        questions = [
            inquirer.List(
                "field",
                message="Update metadata fields:",
                choices=[
                    "Author",
                    "Container title",
                    "Title",
                    "Volume",
                    "Number",
                    "Pages",
                    "Save",
                ],
            ),
        ]
        while True:
            answers = inquirer.prompt(questions)
            user_selection = answers["field"]

            if user_selection == "Save":
                break
            if user_selection == "Author":
                author = input("Authors:")
                record.update_field(
                    key=Fields.AUTHOR, value=author, source="manual_correction"
                )
            elif user_selection == "Container title":
                if Fields.JOURNAL in record.data:
                    journal = input("Journal:")
                    record.update_field(
                        key=Fields.JOURNAL, value=journal, source="manual_correction"
                    )
                if Fields.BOOKTITLE in record.data:
                    booktitle = input("Booktitle:")
                    record.update_field(
                        key=Fields.BOOKTITLE,
                        value=booktitle,
                        source="manual_correction",
                    )
            elif user_selection == "Title":
                title = input("Title:")
                record.update_field(
                    key=Fields.TITLE, value=title, source="manual_correction"
                )
            elif user_selection == "Volume":
                volume = input("Volume:")
                record.update_field(
                    key=Fields.VOLUME, value=volume, source="manual_correction"
                )
            elif user_selection == "Number":
                number = input("Number:")
                record.update_field(
                    key=Fields.NUMBER, value=number, source="manual_correction"
                )
            elif user_selection == "Pages":
                pages = input("Pages:")
                record.update_field(
                    key=Fields.PAGES, value=pages, source="manual_correction"
                )
            user_selection = ""

        return record

    def __open_pdf(self, *, filepath: Path) -> None:
        # pylint: disable=no-member
        webbrowser.open(str(filepath))

    def __remove_page(
        self,
        *,
        user_selection: str,
        filepath: Path,
        pdf_prep_man_operation: colrev.ops.pdf_prep_man.PDFPrepMan,
    ) -> None:
        if user_selection == "Remove coverpage":
            try:
                pdf_prep_man_operation.extract_coverpage(filepath=filepath)
            except colrev_exceptions.InvalidPDFException:
                pass
        elif user_selection == "Remove last page":
            try:
                pdf_prep_man_operation.extract_lastpage(filepath=filepath)
            except colrev_exceptions.InvalidPDFException:
                pass
        elif user_selection == "Remove page range":
            range_str_questions = [
            inquirer.Text('range_str', message="Page range to remove (e.g., 1-3):",
                            validate=lambda _, x: re.match(r"(\d)+-(\d)+", x),
                            )
            ]
            answers = inquirer.prompt(range_str_questions)
            range_str = answers["range_str"]
            pages_to_exclude = list(
                range(
                    int(range_str[: range_str.find("-")])-1,
                    int(range_str[range_str.find("-") + 1 :]),
                )
            )
            try:
                pdf_prep_man_operation.extract_pages(
                    filepath=filepath, pages_to_remove=pages_to_exclude
                )
            except colrev_exceptions.InvalidPDFException:
                pass

    def __is_inside_wsl(self) -> bool:
        return "wsl" in platform.uname().release.lower()

    def __man_pdf_prep_item(
        self,
        *,
        filepath: Path,
        record: colrev.record.Record,
        pdf_prep_man_operation: colrev.ops.pdf_prep_man.PDFPrepMan,
    ) -> None:
        if not self.__is_inside_wsl():
            self.__open_pdf(filepath=filepath)

        # if PDF > 100 pages, we may check on which page we find the title & print

        questions = [
            inquirer.List(
                "prep_decision",
                message="Prepared?",
                choices=[
                    "Yes",
                    "No (delete)",
                    "Skip",
                    "Remove coverpage",
                    "Remove last page",
                    "Remove page range",
                    "Metadata needs to be updated",
                    "Quit",
                ],
            ),
        ]
        while True:
            answers = inquirer.prompt(questions)
            user_selection = answers["prep_decision"]

            # if user_selection.startswith("s"):
            #     if user_selection[1:].isdigit():
            #         self.__to_skip = int(user_selection[1:])
            #     return
            if user_selection in [
                "Remove coverpage",
                "Remove last page",
                "Remove page range",
            ]:
                self.__remove_page(
                    user_selection=user_selection,
                    filepath=filepath,
                    pdf_prep_man_operation=pdf_prep_man_operation,
                )
            elif user_selection == "Yes":
                pdf_prep_man_operation.set_pdf_man_prepared(record=record)
                return
            elif user_selection == "No (delete)":
                record.remove_field(key=Fields.FILE)
                record.remove_field(key=Fields.PDF_ID)
                record.set_status(
                    target_state=colrev.record.RecordState.pdf_needs_manual_retrieval
                )
                if filepath.is_file():
                    filepath.unlink()
                return
            elif user_selection == "Metadata needs to be updated":
                self.__update_metadata(record=record)

            elif user_selection == "Quit":
                raise QuitPressedException()

    def __man_pdf_prep_item_init(
        self,
        *,
        pdf_prep_man_operation: colrev.ops.pdf_prep_man.PDFPrepMan,
        records: dict,
        item: dict,
        stat: str,
    ) -> dict:
        current_platform = platform.system()
        if current_platform in ["Linux", "Darwin"]:
            os.system("clear")
        else:
            os.system("cls")

        print(stat)
        record = colrev.record.Record(data=item)
        record.print_pdf_prep_man()

        record_dict = records[item[Fields.ID]]
        record = colrev.record.Record(data=record_dict)
        if (
            colrev.record.RecordState.pdf_needs_manual_preparation
            != record_dict[Fields.STATUS]
        ):
            return record_dict

        file_provenance = record.get_field_provenance(key=Fields.FILE)
        print(
            "Manual preparation needed:"
            f" {Colors.RED}{file_provenance['note']}{Colors.END}"
        )

        filepath = self.review_manager.path / Path(record_dict[Fields.FILE])
        if not filepath.is_file():
            filepath = self.review_manager.pdf_dir / f"{record_dict['ID']}.pdf"
        record.data.update(colrev_pdf_id=record.get_colrev_pdf_id(pdf_path=filepath))
        if filepath.is_file():
            self.__man_pdf_prep_item(
                filepath=filepath,
                record=record,
                pdf_prep_man_operation=pdf_prep_man_operation,
            )

        else:
            print(f"File does not exist ({record.data[Fields.ID]})")

        self.review_manager.dataset.save_records_dict(records=records)

        return records

    def pdf_prep_man(
        self, pdf_prep_man_operation: colrev.ops.pdf_prep_man.PDFPrepMan, records: dict
    ) -> dict:
        """Prepare PDF manually based on a cli"""

        self.review_manager.logger.info("Loading data for pdf_prep_man")
        pdf_prep_man_data = pdf_prep_man_operation.get_data()
        records = self.review_manager.dataset.load_records_dict()

        for i, item in enumerate(pdf_prep_man_data["items"]):
            if self.__to_skip > 0:
                self.__to_skip -= 1
                continue
            try:
                stat = str(i + 1) + "/" + str(pdf_prep_man_data["nr_tasks"])
                records = self.__man_pdf_prep_item_init(
                    pdf_prep_man_operation=pdf_prep_man_operation,
                    records=records,
                    item=item,
                    stat=stat,
                )
            except QuitPressedException:
                break

        self.review_manager.dataset.save_records_dict(records=records)

        if pdf_prep_man_operation.pdfs_prepared_manually():
            if input("Create commit (y/n)?") == "y":
                self.review_manager.create_commit(
                    msg="Prepare PDFs manually",
                    manual_author=True,
                )
        else:
            self.review_manager.logger.info(
                "Prepare PDFs manually. Afterwards, use colrev pdf-get-man"
            )

        return records


class QuitPressedException(Exception):
    """Quit-pressed exception"""
