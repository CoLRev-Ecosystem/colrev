#! /usr/bin/env python
"""Preparation of curations"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import zope.interface
from dataclasses_jsonschema import JsonSchemaMixin

import colrev.env.package_manager
import colrev.exceptions as colrev_exceptions
import colrev.ops.search_sources
import colrev.record
from colrev.constants import Fields

if TYPE_CHECKING:  # pragma: no cover
    import colrev.ops.prep

# pylint: disable=too-few-public-methods
# pylint: disable=duplicate-code


@zope.interface.implementer(colrev.env.package_manager.PrepPackageEndpointInterface)
@dataclass
class CurationPrep(JsonSchemaMixin):
    """Preparation of curations"""

    settings_class = colrev.env.package_manager.DefaultSettings
    ci_supported: bool = True

    source_correction_hint = "check with the developer"
    always_apply_changes = True

    docs_link = (
        "https://github.com/CoLRev-Environment/colrev/blob/main/"
        + "colrev/ops/built_in/data/colrev_curation.md"
    )

    def __init__(
        self,
        *,
        prep_operation: colrev.ops.prep.Prep,
        settings: dict,
    ) -> None:
        self.settings = self.settings_class.load_settings(data=settings)
        self.quality_model = prep_operation.review_manager.get_qm()
        self.prep_operation = prep_operation
        self.review_manager = prep_operation.review_manager
        self.curation_restrictions = self._load_curation_restrictions()

    def _load_curation_restrictions(self) -> dict:
        curation_restrictions = {}
        curated_endpoints = [
            x
            for x in self.review_manager.settings.data.data_package_endpoints
            if x["endpoint"] == "colrev.colrev_curation"
        ]
        if curated_endpoints:
            curated_endpoint = curated_endpoints[0]
            curation_restrictions = curated_endpoint.get("masterdata_restrictions", {})
        return curation_restrictions

    def _get_applicable_curation_restrictions(
        self, *, record: colrev.record.Record
    ) -> dict:
        """Get the applicable curation restrictions"""

        if not str(record.data.get(Fields.YEAR, "NA")).isdigit():
            return {}

        start_year_values = list(self.curation_restrictions.keys())
        year_index_diffs = [
            int(record.data[Fields.YEAR]) - int(x) for x in start_year_values
        ]
        year_index_diffs = [x if x >= 0 else 2000 for x in year_index_diffs]

        if not year_index_diffs:
            return {}

        index_min = min(range(len(year_index_diffs)), key=year_index_diffs.__getitem__)
        applicable_curation_restrictions = self.curation_restrictions[
            start_year_values[index_min]
        ]
        return applicable_curation_restrictions

    def apply_curation_restrictions(self, *, record: colrev.record.Record) -> None:
        """Apply the curation restrictions"""
        applicable_curation_restrictions = self._get_applicable_curation_restrictions(
            record=record
        )
        if Fields.ENTRYTYPE in applicable_curation_restrictions:
            if applicable_curation_restrictions[Fields.ENTRYTYPE] != record.data.get(
                Fields.ENTRYTYPE, ""
            ):
                try:
                    record.change_entrytype(
                        new_entrytype=applicable_curation_restrictions[
                            Fields.ENTRYTYPE
                        ],
                        qm=self.quality_model,
                    )
                except colrev_exceptions.MissingRecordQualityRuleSpecification as exc:
                    print(exc)

        for field in [Fields.JOURNAL, Fields.BOOKTITLE]:
            if field not in applicable_curation_restrictions:
                continue
            if applicable_curation_restrictions[field] == record.data.get(field, ""):
                continue
            record.update_field(
                key=field,
                value=applicable_curation_restrictions[field],
                source="colrev_curation.curation_restrictions",
            )

        if (
            Fields.VOLUME in applicable_curation_restrictions
            and not applicable_curation_restrictions[Fields.VOLUME]
            and Fields.VOLUME in record.data
        ):
            record.remove_field(
                key=Fields.VOLUME,
                not_missing_note=True,
                source="colrev_curation.curation_restrictions",
            )

        if (
            Fields.NUMBER in applicable_curation_restrictions
            and not applicable_curation_restrictions[Fields.NUMBER]
            and Fields.NUMBER in record.data
        ):
            record.remove_field(
                key=Fields.NUMBER,
                not_missing_note=True,
                source="colrev_curation.curation_restrictions",
            )

    def prepare(
        self,
        record: colrev.record.PrepRecord,
    ) -> colrev.record.Record:
        """Prepare records in a CoLRev curation"""

        if (
            record.data[Fields.STATUS]
            == colrev.record.RecordState.rev_prescreen_excluded
        ):
            return record

        self.apply_curation_restrictions(record=record)

        return record
