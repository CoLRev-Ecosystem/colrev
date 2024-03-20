#!/usr/bin/env python3
"""Remove records, ... from CoLRev projects."""
from __future__ import annotations

from pathlib import Path

import colrev.env.utils
import colrev.operation
from colrev.constants import Fields
from colrev.constants import Filepaths
from colrev.writer.write_utils import write_file


class Remove(colrev.operation.Operation):
    """Remove records, ... from CoLRev projects."""

    def __init__(
        self,
        *,
        review_manager: colrev.review_manager.ReviewManager,
    ) -> None:
        super().__init__(
            review_manager=review_manager,
            operations_type=colrev.operation.OperationsType.check,
            notify_state_transition_operation=False,
        )

    @colrev.operation.Operation.decorate()
    def remove_records(self, *, ids: str) -> None:
        """Remove records from CoLRev project."""

        records = self.review_manager.dataset.load_records_dict()

        for record_id in ids.split(","):
            if record_id in records:
                self.review_manager.logger.info(f" remove {record_id}")
                origins = records[record_id][Fields.ORIGIN]
                if Fields.FILE in records[record_id]:
                    print(f"manually remove file: {records[record_id]['file']}")
                del records[record_id]
                for origin in origins:
                    file, origin_id = origin.split("/")

                    search_dir = self.review_manager.get_path(Filepaths.SEARCH_DIR)
                    filepath = search_dir / Path(file)

                    origin_records = colrev.loader.load_utils.load(
                        filename=filepath,
                        logger=self.review_manager.logger,
                    )

                    if origin_id in origin_records:
                        del origin_records[origin_id]

                    write_file(records_dict=origin_records, filename=filepath)

                    self.review_manager.dataset.add_changes(filepath)

        self.review_manager.dataset.save_records_dict(records)
        self.review_manager.dataset.create_commit(
            msg="Remove records", manual_author=False
        )
