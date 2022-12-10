#! /usr/bin/env python
"""SearchSource: backward search (based on PDFs and GROBID)"""
from __future__ import annotations

import typing
from dataclasses import dataclass
from pathlib import Path

import requests
import zope.interface
from dacite import from_dict
from dataclasses_jsonschema import JsonSchemaMixin

import colrev.env.package_manager
import colrev.exceptions as colrev_exceptions
import colrev.ops.built_in.search_sources.utils as connector_utils
import colrev.ops.search
import colrev.record

# pylint: disable=unused-argument
# pylint: disable=duplicate-code


@zope.interface.implementer(
    colrev.env.package_manager.SearchSourcePackageEndpointInterface
)
@dataclass
class BackwardSearchSource(JsonSchemaMixin):
    """Performs a backward search extracting references from PDFs using GROBID
    Scope: all included papers with colrev_status in (rev_included, rev_synthesized)
    """

    settings_class = colrev.env.package_manager.DefaultSourceSettings
    source_identifier = "{{cited_by_file}} (references)"
    search_type = colrev.settings.SearchType.BACKWARD_SEARCH
    heuristic_status = colrev.env.package_manager.SearchSourceHeuristicStatus.supported
    short_name = "PDF backward search"
    link = "https://github.com/kermitt2/grobid"

    def __init__(
        self, *, source_operation: colrev.operation.CheckOperation, settings: dict
    ) -> None:

        self.search_source = from_dict(data_class=self.settings_class, data=settings)
        self.grobid_service = source_operation.review_manager.get_grobid_service()
        self.grobid_service.start()

    def __bw_search_condition(self, *, record: dict) -> bool:
        # rev_included/rev_synthesized
        if "colrev_status" in self.search_source.search_parameters["scope"]:
            if (
                self.search_source.search_parameters["scope"]["colrev_status"]
                == "rev_included|rev_synthesized"
            ) and record["colrev_status"] not in [
                colrev.record.RecordState.rev_included,
                colrev.record.RecordState.rev_synthesized,
            ]:
                return False

        # Note: this is for peer_reviews
        if "file" in self.search_source.search_parameters["scope"]:
            if (
                self.search_source.search_parameters["scope"]["file"] == "paper.pdf"
            ) and "data/pdfs/paper.pdf" != record.get("file", ""):
                return False

        return True

    def validate_source(
        self,
        search_operation: colrev.ops.search.Search,
        source: colrev.settings.SearchSource,
    ) -> None:
        """Validate the SearchSource (parameters etc.)"""

        search_operation.review_manager.logger.debug(
            f"Validate SearchSource {source.filename}"
        )

        if source.source_identifier != self.source_identifier:
            raise colrev_exceptions.InvalidQueryException(
                f"Invalid source_identifier: {source.source_identifier} "
                f"(should be {self.source_identifier})"
            )

        if "scope" not in source.search_parameters:
            raise colrev_exceptions.InvalidQueryException(
                "Scope required in the search_parameters"
            )

        if source.search_parameters["scope"].get("file", "") == "paper.md":
            pass
        else:
            if (
                source.search_parameters["scope"]["colrev_status"]
                != "rev_included|rev_synthesized"
            ):
                raise colrev_exceptions.InvalidQueryException(
                    "search_parameters/scope/colrev_status must be rev_included|rev_synthesized"
                )

        search_operation.review_manager.logger.debug(
            f"SearchSource {source.filename} validated"
        )

    def run_search(
        self, search_operation: colrev.ops.search.Search, update_only: bool
    ) -> None:
        """Run a search of PDFs (backward search based on GROBID)"""

        if not search_operation.review_manager.dataset.records_file.is_file():
            print("No records imported. Cannot run backward search yet.")
            return

        records = search_operation.review_manager.dataset.load_records_dict()

        pdf_backward_search_feed = connector_utils.GeneralOriginFeed(
            source_operation=search_operation,
            source=self.search_source,
            feed_file=self.search_source.filename,
            update_only=False,
            key="bwsearch_ref",
        )

        for record in records.values():
            if not self.__bw_search_condition(record=record):
                continue

            # TODO : IDs generated by GROBID for cited refernces may change across grobid versions
            # -> challenge for key-handling/updating searches...

            pdf_path = search_operation.review_manager.path / Path(record["file"])
            if not Path(pdf_path).is_file():
                search_operation.review_manager.logger.error(
                    f'File not found for {record["ID"]}'
                )
                continue

            search_operation.review_manager.logger.info(
                f'Running backward search for {record["ID"]} ({record["file"]})'
            )

            # pylint: disable=consider-using-with
            options = {"consolidateHeader": "0", "consolidateCitations": "0"}
            ret = requests.post(
                self.grobid_service.GROBID_URL + "/api/processReferences",
                files={str(pdf_path): open(pdf_path, "rb", encoding="utf8")},
                data=options,
                headers={"Accept": "application/x-bibtex"},
                timeout=30,
            )

            new_records_dict = (
                search_operation.review_manager.dataset.load_records_dict(
                    load_str=ret.text
                )
            )
            new_records = list(new_records_dict.values())
            for new_record in new_records:
                new_record["bwsearch_ref"] = (
                    record["ID"] + "_backward_search_" + new_record["ID"]
                )
                new_record["cited_by"] = record["ID"]
                new_record["cited_by_file"] = record["file"]
                pdf_backward_search_feed.set_id(record_dict=new_record)
                pdf_backward_search_feed.add_record(
                    record=colrev.record.Record(data=new_record),
                )

        pdf_backward_search_feed.save_feed_file()

        if search_operation.review_manager.dataset.has_changes():
            search_operation.review_manager.create_commit(
                msg="Backward search", script_call="colrev search"
            )
        else:
            print("No new records added.")

    @classmethod
    def heuristic(cls, filename: Path, data: str) -> dict:
        """Source heuristic for PDF backward searches (GROBID)"""

        result = {"confidence": 0.0}
        if str(filename).endswith("_ref_list.pdf"):
            result["confidence"] = 1.0
            return result
        return result

    def load_fixes(
        self,
        load_operation: colrev.ops.load.Load,
        source: colrev.settings.SearchSource,
        records: typing.Dict,
    ) -> dict:
        """Load fixes for PDF backward searches (GROBID)"""

        return records

    def prepare(
        self, record: colrev.record.Record, source: colrev.settings.SearchSource
    ) -> colrev.record.Record:
        """Source-specific preparation for PDF backward searches (GROBID)"""

        if "misc" == record.data["ENTRYTYPE"] and "publisher" in record.data:
            record.data["ENTRYTYPE"] = "book"

        return record


if __name__ == "__main__":
    pass
