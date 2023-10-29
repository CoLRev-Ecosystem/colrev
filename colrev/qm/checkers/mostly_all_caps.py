#! /usr/bin/env python
"""Checker for mostly-all-caps fields."""
from __future__ import annotations

import colrev.env.utils
import colrev.qm.quality_model
from colrev.constants import DefectCodes
from colrev.constants import Fields
from colrev.constants import FieldValues

# pylint: disable=too-few-public-methods


class MostlyAllCapsFieldChecker:
    """The MostlyAllCapsFieldChecker"""

    msg = DefectCodes.MOSTLY_ALL_CAPS

    def __init__(self, quality_model: colrev.qm.quality_model.QualityModel) -> None:
        self.quality_model = quality_model

    def run(self, *, record: colrev.record.Record) -> None:
        """Run the mostly-all-caps checks"""
        for key in [
            Fields.AUTHOR,
            Fields.TITLE,
            Fields.JOURNAL,
            Fields.BOOKTITLE,
            Fields.EDITOR,
        ]:
            if (
                key not in record.data
                or record.ignored_defect(field=key, defect=self.msg)
                or record.data[key] == FieldValues.UNKNOWN
            ):
                continue

            if self.__is_mostly_all_caps(record=record, key=key):
                record.add_masterdata_provenance_note(key=key, note=self.msg)
            else:
                record.remove_masterdata_provenance_note(key=key, note=self.msg)

    def __is_mostly_all_caps(self, *, record: colrev.record.Record, key: str) -> bool:
        """Check if the field is mostly all caps"""

        # Online sources/software can be short/have caps
        if (
            record.data["ENTRYTYPE"] == "online"
            and key == Fields.TITLE
            and len(record.data[Fields.TITLE]) < 10
        ):
            return False

        if (
            colrev.env.utils.percent_upper_chars(record.data[key].replace(" and ", ""))
            < 0.7
        ):
            return False

        # container-title-abbreviated
        if key in [Fields.JOURNAL, Fields.BOOKTITLE] and len(record.data[key]) < 6:
            return False

        if record.data[key] == "PLoS ONE":
            return False

        return True


def register(quality_model: colrev.qm.quality_model.QualityModel) -> None:
    """Register the checker"""
    quality_model.register_checker(MostlyAllCapsFieldChecker(quality_model))
