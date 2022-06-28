#!/usr/bin/env python3
import importlib
import io
import logging
import os
import pprint
import re
import shutil
import sys
import tempfile
import typing
from contextlib import redirect_stdout
from dataclasses import asdict
from enum import Enum
from importlib.metadata import version
from pathlib import Path

import git
import yaml
from dacite import from_dict

from colrev_core import review_dataset
from colrev_core.data import ManuscriptRecordSourceTagError
from colrev_core.environment import EnvironmentManager
from colrev_core.process import Process
from colrev_core.process import ProcessType
from colrev_core.process import UnstagedGitChangesError
from colrev_core.review_dataset import DuplicatesError
from colrev_core.review_dataset import FieldError
from colrev_core.review_dataset import OriginError
from colrev_core.review_dataset import PropagatedIDChange
from colrev_core.settings import Configuration


class ReviewManager:
    """
    Class for managing individual CoLRev review project (repositories)
    """

    notified_next_process = None
    """ReviewManager was notified for the upcoming process and
    will provide access to the ReviewDataset"""

    def __init__(
        self,
        *,
        path_str: str = None,
        force_mode: bool = False,
        debug_mode: bool = False,
    ) -> None:
        from colrev_core.review_dataset import ReviewDataset

        self.force_mode = force_mode
        """Force mode variable (bool)"""

        if path_str is not None:
            self.path = Path(path_str)
            """Path of the project repository"""
        else:
            self.path = Path.cwd()

        if debug_mode:
            self.DEBUG_MODE = True
        else:
            self.DEBUG_MODE = False

        try:
            self.paths = self.__get_file_paths(repository_dir_str=self.path)

            self.settings = self.load_settings()
        except Exception as e:
            if force_mode:
                print(e)
                pass
            else:
                raise e

        try:
            if self.DEBUG_MODE:
                self.report_logger = self.__setup_report_logger(level=logging.DEBUG)
                """Logger for the commit report"""
                self.logger = self.__setup_logger(level=logging.DEBUG)
                """Logger for processing information"""
            else:
                self.report_logger = self.__setup_report_logger(level=logging.INFO)
                self.logger = self.__setup_logger(level=logging.INFO)
        except Exception as e:
            if force_mode:
                print(e)
                pass
            else:
                raise e

        try:
            global_git_vars = EnvironmentManager.get_name_mail_from_global_git_config()
            if 2 != len(global_git_vars):
                logging.error(
                    "Global git variables (user name and email) not available."
                )
                return
            self.COMMITTER, self.EMAIL = global_git_vars

            self.pp = pprint.PrettyPrinter(indent=4, width=140, compact=False)
            self.REVIEW_DATASET = ReviewDataset(REVIEW_MANAGER=self)
            """The review dataset object"""
            self.sources = self.REVIEW_DATASET.load_sources()
            """Information on sources (search directory)"""
        except Exception as e:
            if force_mode:
                print(e)
                pass
            else:
                raise e

        if self.DEBUG_MODE:
            print("\n\n")
            self.logger.debug("Created review manager instance")
            self.logger.debug(f"Settings:\n{self.settings}")

    def load_settings(self) -> Configuration:
        import dacite
        import json
        import pkgutil

        # https://tech.preferred.jp/en/blog/working-with-configuration-in-python/

        # possible extension : integrate/merge global, default settings
        # from colrev_core.environment import EnvironmentManager
        # def selective_merge(base_obj, delta_obj):
        #     if not isinstance(base_obj, dict):
        #         return delta_obj
        #     common_keys = set(base_obj).intersection(delta_obj)
        #     new_keys = set(delta_obj).difference(common_keys)
        #     for k in common_keys:
        #         base_obj[k] = selective_merge(base_obj[k], delta_obj[k])
        #     for k in new_keys:
        #         base_obj[k] = delta_obj[k]
        #     return base_obj
        # print(selective_merge(default_settings, project_settings))

        if not self.paths["SETTINGS"].is_file():
            filedata = pkgutil.get_data(__name__, "template/settings.json")
            if filedata:
                settings = json.loads(filedata.decode("utf-8"))
                with open(self.paths["SETTINGS"], "w", encoding="utf8") as file:
                    json.dump(settings, file, indent=4)

        with open(self.paths["SETTINGS"]) as f:
            loaded_settings = json.load(f)

        converters = {Path: Path, Enum: Enum}

        # TODO : check validation
        # (e..g, non-float values for prep/similarity do not through errors)

        settings = from_dict(
            data_class=Configuration,
            data=loaded_settings,
            config=dacite.Config(type_hooks=converters, cast=[Enum]),  # type: ignore
        )

        return settings

    def save_settings(self) -> None:
        import json

        def custom_asdict_factory(data):
            def convert_value(obj):
                if isinstance(obj, Enum):
                    return obj.value
                if isinstance(obj, Path):
                    return str(obj)
                return obj

            return {k: convert_value(v) for k, v in data}

        exported_dict = asdict(self.settings, dict_factory=custom_asdict_factory)
        with open("settings.json", "w") as outfile:
            json.dump(exported_dict, outfile, indent=4)
        self.REVIEW_DATASET.add_changes(path="settings.json")

        return

    def __get_file_paths(self, *, repository_dir_str: Path) -> dict:
        repository_dir = repository_dir_str
        main_refs = "references.bib"
        data = "data.csv"
        pdf_dir = "pdfs"
        paper = "paper.md"
        readme = "readme.md"
        report = "report.log"
        search_dir = "search"
        status = "status.yaml"
        corrections = ".corrections"
        settings = "settings.json"
        return {
            "REPO_DIR": repository_dir,
            "MAIN_REFERENCES_RELATIVE": Path(main_refs),
            "MAIN_REFERENCES": repository_dir.joinpath(main_refs),
            "DATA_RELATIVE": Path(data),
            "DATA": repository_dir.joinpath(data),
            "PDF_DIRECTORY_RELATIVE": Path(pdf_dir),
            "PDF_DIRECTORY": repository_dir.joinpath(pdf_dir),
            "PAPER_RELATIVE": Path(paper),
            "PAPER": repository_dir.joinpath(paper),
            "README_RELATIVE": Path(readme),
            "README": repository_dir.joinpath(readme),
            "REPORT_RELATIVE": Path(report),
            "REPORT": repository_dir.joinpath(report),
            "SEARCHDIR_RELATIVE": Path(search_dir),
            "SEARCHDIR": repository_dir.joinpath(search_dir),
            "STATUS_RELATIVE": Path(status),
            "STATUS": repository_dir.joinpath(status),
            "CORRECTIONS_PATH": repository_dir.joinpath(corrections),
            "SETTINGS": repository_dir.joinpath(settings),
            "SETTINGS_RELATIVE": Path(settings),
        }

    def get_remote_url(self):
        git_repo = self.REVIEW_DATASET.get_repo()
        for remote in git_repo.remotes:
            if remote.url:
                remote_url = remote.url.rstrip(".git")
                return remote_url

        return None

    def __actor_fallback(self) -> str:
        from colrev_core.environment import EnvironmentManager

        name = EnvironmentManager.get_name_mail_from_global_git_config()[0]
        return name

    def __email_fallback(self) -> str:
        from colrev_core.environment import EnvironmentManager

        email = EnvironmentManager.get_name_mail_from_global_git_config()[1]
        return email

    def __setup_logger(self, *, level=logging.INFO) -> logging.Logger:
        # for logger debugging:
        # from logging_tree import printout
        # printout()
        logger = logging.getLogger(f"colrev_core{str(self.path).replace('/', '_')}")

        logger.setLevel(level)

        if logger.handlers:
            for handler in logger.handlers:
                logger.removeHandler(handler)

        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        handler.setLevel(level)

        logger.addHandler(handler)
        logger.propagate = False

        return logger

    def __setup_report_logger(self, *, level=logging.INFO) -> logging.Logger:
        report_logger = logging.getLogger(
            f"colrev_core_report{str(self.path).replace('/', '_')}"
        )

        if report_logger.handlers:
            for handler in report_logger.handlers:
                report_logger.removeHandler(handler)

        report_logger.setLevel(level)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        report_file_handler = logging.FileHandler("report.log", mode="a")
        report_file_handler.setFormatter(formatter)

        report_logger.addHandler(report_file_handler)

        if logging.DEBUG == level:
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            report_logger.addHandler(handler)
        report_logger.propagate = False

        return report_logger

    def __get_colrev_versions(self) -> typing.List[str]:

        current_colrev_core_version = version("colrev_core")
        last_colrev_core_version = current_colrev_core_version

        last_commit_message = self.REVIEW_DATASET.get_commit_message(commit_nr=0)
        cmsg_lines = last_commit_message.split("\n")
        for cmsg_line in cmsg_lines[0:100]:
            if "colrev_core" in cmsg_line and "version" in cmsg_line:
                last_colrev_core_version = cmsg_line[cmsg_line.find("version ") + 8 :]

        return [last_colrev_core_version, current_colrev_core_version]

    def __check_software(self) -> None:
        last_version, current_version = self.__get_colrev_versions()
        if last_version != current_version:
            raise SoftwareUpgradeError(last_version, current_version)
        return

    def upgrade_colrev(self) -> None:
        from colrev_core.process import CheckProcess

        last_version, current_version = self.__get_colrev_versions()

        if "+" in last_version:
            last_version = last_version[: last_version.find("+")]
        if "+" in current_version:
            current_version = current_version[: current_version.find("+")]

        cur_major = current_version[: current_version.rfind(".")]
        next_minor = str(int(current_version[current_version.rfind(".") + 1 :]) + 1)
        upcoming_version = cur_major + "." + next_minor

        CheckProcess(REVIEW_MANAGER=self)  # to notify

        def inplace_change(filename: Path, old_string: str, new_string: str) -> None:
            with open(filename, encoding="utf8") as f:
                s = f.read()
                if old_string not in s:
                    logging.info(f'"{old_string}" not found in {filename}.')
                    return
            with open(filename, "w", encoding="utf8") as f:
                s = s.replace(old_string, new_string)
                f.write(s)
            return

        def retrieve_package_file(*, template_file: Path, target: Path) -> None:
            import pkgutil

            filedata = pkgutil.get_data(__name__, str(template_file))
            if filedata:
                with open(target, "w", encoding="utf8") as file:
                    file.write(filedata.decode("utf-8"))
            return

        def migrate_0_3_0(self) -> bool:
            records = self.REVIEW_DATASET.load_records_dict()
            if len(records.values()) > 0:
                for record in records.values():
                    if "LOCAL_INDEX" == record.get("metadata_source", ""):
                        record["metadata_source"] = "CURATED"
                    if "pdf_hash" in record:
                        record["colrev_pdf_id"] = "cpid1:" + record["pdf_hash"]
                        del record["pdf_hash"]

                self.REVIEW_DATASET.save_records_dict(records=records)
                self.REVIEW_DATASET.add_record_changes()

            inplace_change(
                self.paths["SOURCES"], "search_type: LOCAL_PAPER_INDEX", "PDFS"
            )
            self.REVIEW_DATASET.add_changes(path=str(self.paths["SOURCES_RELATIVE"]))

            if self.REVIEW_DATASET.has_changes():
                return True
            return False

        def migrate_0_4_0(self) -> bool:
            import pandas as pd
            import yaml
            import json
            import pkgutil

            if not Path("settings.json").is_file():
                filedata = pkgutil.get_data(__name__, "template/settings.json")
                if not filedata:
                    print("error reading file")
                    return False
                settings = json.loads(filedata.decode("utf-8"))
            else:
                with open("settings.json") as f:
                    settings = json.load(f)

            old_sources_path = Path("sources.yaml")
            if old_sources_path.is_file():
                if old_sources_path.is_file():
                    with open(old_sources_path) as f:
                        sources_df = pd.json_normalize(yaml.safe_load(f))
                        sources = sources_df.to_dict("records")
                        print(sources)
                for source in sources:
                    if len(source["search_parameters"]) > 0:
                        if "dblp" == source["search_parameters"][0]["endpoint"]:
                            source["source_identifier"] = "{{dblp_key}}"
                        elif "crossref" == source["search_parameters"][0]["endpoint"]:
                            source[
                                "source_identifier"
                            ] = "https://api.crossref.org/works/{{doi}}"
                        elif (
                            "pdfs_directory"
                            == source["search_parameters"][0]["endpoint"]
                        ):
                            source["source_identifier"] = "{{file}}"
                        else:
                            source["source_identifier"] = source["search_parameters"][
                                0
                            ]["endpoint"]

                        source["search_parameters"] = source["search_parameters"][0][
                            "params"
                        ]
                    else:
                        source["search_parameters"] = ""
                        source["source_identifier"] = source.get("source_url", "")

                    if (
                        source["comment"] != source["comment"]
                        or "NA" == source["comment"]
                    ):  # NaN
                        source["comment"] = ""

                    if "source_url" in source:
                        del source["source_url"]
                    if "source_name" in source:
                        del source["source_name"]
                    if "last_sync" in source:
                        del source["last_sync"]

                settings["search"]["sources"] = sources

            if any(r["name"] == "exclusion" for r in settings["prep"]["prep_rounds"]):
                e_r = [
                    r
                    for r in settings["prep"]["prep_rounds"]
                    if r["name"] == "exclusion"
                ][0]
                if "exclude_predatory_journals" in e_r["scripts"]:
                    e_r["scripts"].remove("exclude_predatory_journals")
            settings["prescreen"]["scope"] = [{"LanguageScope": ["en"]}]
            if "plugin" in settings["prescreen"]:
                del settings["prescreen"]["plugin"]
            if "mode" in settings["prescreen"]:
                del settings["prescreen"]["mode"]
            settings["prescreen"]["scripts"] = [
                {"endpoint": "scope_prescreen"},
                {"endpoint": "colrev_cli_prescreen"},
            ]
            if "process" in settings["screen"]:
                del settings["screen"]["process"]
            settings["screen"]["scripts"] = [{"endpoint": "colrev_cli_screen"}]
            settings["pdf_get"]["scripts"] = [
                {"endpoint": "unpaywall"},
                {"endpoint": "local_index"},
            ]

            settings["pdf_prep"]["scripts"] = [
                {"endpoint": "pdf_check_ocr"},
                {"endpoint": "remove_coverpage"},
                {"endpoint": "remove_last_page"},
                {"endpoint": "validate_pdf_metadata"},
                {"endpoint": "validate_completeness"},
            ]

            for x in settings["data"]["data_format"]:
                if "MANUSCRIPT" == x["endpoint"]:
                    if "paper_endpoint_version" not in x:
                        x["paper_endpoint_version"] = "0.1"
                if "STRUCTURED" == x["endpoint"]:
                    if "structured_data_endpoint_version" not in x:
                        x["structured_data_endpoint_version"] = "0.1"

            if "curated_metadata" in str(self.path):
                repo = git.Repo(str(self.path))
                settings["project"]["curation_url"] = repo.remote().url.replace(
                    ".git", ""
                )

            if old_sources_path.is_file():
                old_sources_path.unlink()
                self.REVIEW_DATASET.remove_file_from_git(path=str(old_sources_path))

            if Path("shared_config.ini").is_file():
                Path("shared_config.ini").unlink()
                self.REVIEW_DATASET.remove_file_from_git(path="shared_config.ini")
            if Path("private_config.ini").is_file():
                Path("private_config.ini").unlink()

            if "curated_metadata" in str(self.path):
                settings["project"]["curated_masterdata"] = True
                settings["project"]["curated_fields"] = [
                    "doi",
                    "url",
                    "dblp_key",
                ]

            settings["dedupe"]["same_source_merges"] = "prevent"

            with open("settings.json", "w") as outfile:
                json.dump(settings, outfile, indent=4)

            self.settings = self.load_settings()
            self.save_settings()
            self.REVIEW_DATASET.add_setting_changes()
            self.sources = self.REVIEW_DATASET.load_sources()
            records = self.REVIEW_DATASET.load_records_dict()
            if len(records.values()) > 0:
                for record in records.values():
                    if "manual_duplicate" in record:
                        del record["manual_duplicate"]
                    if "manual_non_duplicate" in record:
                        del record["manual_non_duplicate"]
                    if "origin" in record:
                        record["colrev_origin"] = record["origin"]
                        del record["origin"]
                    if "status" in record:
                        record["colrev_status"] = record["status"]
                        del record["status"]
                    if "excl_criteria" in record:
                        record["exclusion_criteria"] = record["excl_criteria"]
                        del record["excl_criteria"]
                    if "metadata_source" in record:
                        del record["metadata_source"]

                    if "colrev_masterdata" in record:
                        if record["colrev_masterdata"] == "ORIGINAL":
                            del record["colrev_masterdata"]
                        else:
                            record["colrev_masterdata_provenance"] = record[
                                "colrev_masterdata"
                            ]
                            del record["colrev_masterdata"]

                    if "curated_metadata" in str(self.path):
                        if "colrev_masterdata_provenance" in record:
                            if "CURATED" == record["colrev_masterdata_provenance"]:
                                record["colrev_masterdata_provenance"] = {}
                    if "colrev_masterdata_provenance" not in record:
                        record["colrev_masterdata_provenance"] = {}
                    if "colrev_data_provenance" not in record:
                        record["colrev_data_provenance"] = {}

                    # if "source_url" in record:
                    #     record["colrev_masterdata"] = \
                    #           "CURATED:" + record["source_url"]
                    #     del record["source_url"]
                    # else:
                    #     record["colrev_masterdata"] = "ORIGINAL"
                    # Note : for curated repositories
                    # record["colrev_masterdata"] = "CURATED"

                self.REVIEW_DATASET.save_records_dict(records=records)
                self.REVIEW_DATASET.add_record_changes()

            retrieve_package_file(
                template_file=Path("template/.pre-commit-config.yaml"),
                target=Path(".pre-commit-config.yaml"),
            )

            self.REVIEW_DATASET.add_changes(path=".pre-commit-config.yaml")
            # Note: the order is important in this case.
            self.REVIEW_DATASET.update_colrev_ids()

            return True

        def migrate_0_5_0(self) -> None:

            return

        # next version should be:
        # ...
        # {'from': '0.4.0', "to": '0.5.0', 'script': migrate_0_4_0}
        # {'from': '0.5.0', "to": upcoming_version, 'script': migrate_0_5_0}
        migration_scripts: typing.List[typing.Dict[str, typing.Any]] = [
            {"from": "0.3.0", "to": "0.4.0", "script": migrate_0_3_0},
            {"from": "0.4.0", "to": "0.5.0", "script": migrate_0_4_0},
            {"from": "0.5.0", "to": upcoming_version, "script": migrate_0_5_0},
        ]

        # Start with the first step if the version is older:
        if last_version not in [x["from"] for x in migration_scripts]:
            last_version = "0.3.0"

        while current_version in [x["from"] for x in migration_scripts]:
            self.logger.info(f"Current CoLRev version: {last_version}")

            migrator = [x for x in migration_scripts if x["from"] == last_version].pop()

            migration_script = migrator["script"]

            self.logger.info(f"Migrating from {migrator['from']} to {migrator['to']}")

            updated = migration_script(self)
            if updated:
                self.logger.info(f"Updated to: {last_version}")
            else:
                self.logger.info("Nothing to do.")
                self.logger.info(
                    "If the update notification occurs again, run\n "
                    "git commit -n -m --allow-empty 'update colrev'"
                )

            # Note : the version in the commit message will be set to
            # the current_version immediately. Therefore, use the migrator['to'] field.
            last_version = migrator["to"]

            if last_version == upcoming_version:
                break

        if self.REVIEW_DATASET.has_changes():
            self.create_commit(msg=f"Upgrade to CoLRev {upcoming_version}")
        else:
            self.logger.info("Nothing to do.")
            self.logger.info(
                "If the update notification occurs again, run\n "
                "git commit -n -m --allow-empty 'update colrev'"
            )

        return

    def check_repository_setup(self) -> None:
        from git.exc import GitCommandError

        # 1. git repository?
        if not self.__is_git_repo(path=self.paths["REPO_DIR"]):
            raise RepoSetupError("no git repository. Use colrev_core init")

        # 2. colrev_core project?
        if not self.__is_colrev_core_project():
            raise RepoSetupError(
                "No colrev_core repository."
                + "To retrieve a shared repository, use colrev_core init."
                + "To initalize a new repository, "
                + "execute the command in an empty directory."
            )

        installed_hooks = self.__get_installed_hooks()

        # 3. Pre-commit hooks installed?
        self.__require_hooks_installed(installed_hooks=installed_hooks)

        # 4. Pre-commit hooks up-to-date?
        try:
            if not self.__hooks_up_to_date(installed_hooks=installed_hooks):
                raise RepoSetupError(
                    "Pre-commit hooks not up-to-date. Use\n"
                    + "colrev config --update_hooks"
                )
                # This could also be a warning, but hooks should not change often.

        except GitCommandError:
            self.logger.warning(
                "No Internet connection, cannot check remote "
                "colrev-hooks repository for updates."
            )
        return

    def __get_base_prefix_compat(self) -> str:
        return (
            getattr(sys, "base_prefix", None)
            or getattr(sys, "real_prefix", None)
            or sys.prefix
        )

    def in_virtualenv(self) -> bool:
        return self.__get_base_prefix_compat() != sys.prefix

    def __check_git_conflicts(self) -> None:
        # Note: when check is called directly from the command line.
        # pre-commit hooks automatically notify on merge conflicts

        git_repo = git.Repo(str(self.paths["REPO_DIR"]))
        unmerged_blobs = git_repo.index.unmerged_blobs()

        for path in unmerged_blobs:
            list_of_blobs = unmerged_blobs[path]
            for (stage, blob) in list_of_blobs:
                if stage != 0:
                    raise GitConflictError(path)
        return

    def __is_git_repo(self, *, path: Path) -> bool:
        from git.exc import InvalidGitRepositoryError

        try:
            _ = git.Repo(str(path)).git_dir
            return True
        except InvalidGitRepositoryError:
            return False

    def __is_colrev_core_project(self) -> bool:
        required_paths = [
            Path(".pre-commit-config.yaml"),
            Path(".gitignore"),
            Path("settings.json"),
        ]
        if not all((self.path / x).is_file() for x in required_paths):
            return False
        return True

    def __get_installed_hooks(self) -> dict:
        installed_hooks: dict = {"hooks": list()}
        with open(".pre-commit-config.yaml", encoding="utf8") as pre_commit_y:
            pre_commit_config = yaml.load(pre_commit_y, Loader=yaml.FullLoader)
        installed_hooks[
            "remote_pv_hooks_repo"
        ] = "https://github.com/geritwagner/colrev-hooks"
        for repository in pre_commit_config["repos"]:
            if repository["repo"] == installed_hooks["remote_pv_hooks_repo"]:
                installed_hooks["local_hooks_version"] = repository["rev"]
                installed_hooks["hooks"] = [hook["id"] for hook in repository["hooks"]]
        return installed_hooks

    def __lsremote(self, *, url: str) -> dict:
        remote_refs = {}
        g = git.cmd.Git()
        for ref in g.ls_remote(url).split("\n"):
            hash_ref_list = ref.split("\t")
            remote_refs[hash_ref_list[1]] = hash_ref_list[0]
        return remote_refs

    def __hooks_up_to_date(self, *, installed_hooks: dict) -> bool:
        refs = self.__lsremote(url=installed_hooks["remote_pv_hooks_repo"])
        remote_sha = refs["HEAD"]
        if remote_sha == installed_hooks["local_hooks_version"]:
            return True
        return False

    def __require_hooks_installed(self, *, installed_hooks: dict) -> bool:
        required_hooks = ["check", "format", "report", "sharing"]
        hooks_activated = set(installed_hooks["hooks"]) == set(required_hooks)
        if not hooks_activated:
            missing_hooks = [
                x for x in required_hooks if x not in installed_hooks["hooks"]
            ]
            raise RepoSetupError(
                f"missing hooks in .pre-commit-config.yaml ({missing_hooks})"
            )

        pch_file = Path(".git/hooks/pre-commit")
        if pch_file.is_file():
            with open(pch_file, encoding="utf8") as f:
                if "File generated by pre-commit" not in f.read(4096):
                    raise RepoSetupError(
                        "pre-commit hooks not installed (use pre-commit install)"
                    )
        else:
            raise RepoSetupError(
                "pre-commit hooks not installed (use pre-commit install)"
            )

        psh_file = Path(".git/hooks/pre-push")
        if psh_file.is_file():
            with open(psh_file, encoding="utf8") as f:
                if "File generated by pre-commit" not in f.read(4096):
                    raise RepoSetupError(
                        "pre-commit push hooks not installed "
                        "(use pre-commit install --hook-type pre-push)"
                    )
        else:
            raise RepoSetupError(
                "pre-commit push hooks not installed "
                "(use pre-commit install --hook-type pre-push)"
            )

        pcmh_file = Path(".git/hooks/prepare-commit-msg")
        if pcmh_file.is_file():
            with open(pcmh_file, encoding="utf8") as f:
                if "File generated by pre-commit" not in f.read(4096):
                    raise RepoSetupError(
                        "pre-commit prepare-commit-msg hooks not installed "
                        "(use pre-commit install --hook-type prepare-commit-msg)"
                    )
        else:
            raise RepoSetupError(
                "pre-commit prepare-commit-msg hooks not installed "
                "(use pre-commit install --hook-type prepare-commit-msg)"
            )

        return True

    def check_repo(self) -> dict:
        """Check whether the repository is in a consistent state
        Entrypoint for pre-commit hooks
        """
        # Note : we have to return status code and message
        # because printing from other packages does not work in pre-commit hook.

        from colrev_core.environment import EnvironmentManager

        # We work with exceptions because each issue may be raised in different checks.
        self.notified_next_process = ProcessType.check
        PASS, FAIL = 0, 1
        check_scripts: typing.List[typing.Dict[str, typing.Any]] = [
            {"script": EnvironmentManager.check_git_installed, "params": []},
            {"script": EnvironmentManager.check_docker_installed, "params": []},
            {"script": EnvironmentManager.build_docker_images, "params": []},
            {"script": self.__check_git_conflicts, "params": []},
            {"script": self.check_repository_setup, "params": []},
            {"script": self.__check_software, "params": []},
        ]

        not self.paths["SEARCHDIR"].mkdir(exist_ok=True)

        failure_items = []
        if not self.paths["MAIN_REFERENCES"].is_file():
            self.logger.debug("Checks for MAIN_REFERENCES not activated")
        else:

            # Note : retrieving data once is more efficient than
            # reading the MAIN_REFERENCES multiple times (for each check)

            if self.REVIEW_DATASET.file_in_history(
                filepath=self.paths["MAIN_REFERENCES_RELATIVE"]
            ):
                prior = self.REVIEW_DATASET.retrieve_prior()
                self.logger.debug("prior")
                self.logger.debug(self.pp.pformat(prior))
            else:  # if MAIN_REFERENCES not yet in git history
                prior = {}

            data = self.REVIEW_DATASET.retrieve_data(prior=prior)
            self.logger.debug("data")
            self.logger.debug(self.pp.pformat(data))

            main_refs_checks = [
                {
                    "script": self.REVIEW_DATASET.check_persisted_ID_changes,
                    "params": {"prior": prior, "data": data},
                },
                {"script": self.REVIEW_DATASET.check_sources, "params": []},
                {
                    "script": self.REVIEW_DATASET.check_main_references_duplicates,
                    "params": {"data": data},
                },
                {
                    "script": self.REVIEW_DATASET.check_main_references_origin,
                    "params": {"prior": prior, "data": data},
                },
                {
                    "script": self.REVIEW_DATASET.check_status_fields,
                    "params": {"data": data},
                },
                {
                    "script": self.REVIEW_DATASET.check_status_transitions,
                    "params": {"data": data},
                },
                {
                    "script": self.REVIEW_DATASET.check_main_references_screen,
                    "params": {"data": data},
                },
            ]

            if prior == {}:  # Selected checks if MAIN_REFERENCES not yet in git history
                main_refs_checks = [
                    x
                    for x in main_refs_checks
                    if x["script"]
                    in [
                        "check_sources",
                        "check_main_references_duplicates",
                    ]
                ]

            check_scripts += main_refs_checks

            self.logger.debug("Checks for MAIN_REFERENCES activated")

            PAPER = self.paths["PAPER"]
            if not PAPER.is_file():
                self.logger.debug("Checks for PAPER not activated\n")
            else:
                from colrev_core.data import Data, ManuscriptEndpoint

                DATA = Data(self, notify_state_transition_process=False)
                manuscript_checks = [
                    {
                        "script": ManuscriptEndpoint.check_new_record_source_tag,
                        "params": [self],
                    },
                    {
                        "script": DATA.main,
                        "params": [True],
                    },
                    {
                        "script": self.update_status_yaml,
                        "params": [],
                    },
                ]
                check_scripts += manuscript_checks
                self.logger.debug("Checks for PAPER activated\n")

            # TODO: checks for structured data
            # See functions in comments
            # if DATA.is_file():
            #     data = pd.read_csv(DATA, dtype=str)
            #     check_duplicates_data(data)
            # check_screen_data(screen, data)
            # DATA = REVIEW_MANAGER.paths['DATA']

        for check_script in check_scripts:
            try:
                if [] == check_script["params"]:
                    self.logger.debug(f'{check_script["script"].__name__}() called')
                    check_script["script"]()
                else:
                    self.logger.debug(
                        f'{check_script["script"].__name__}(params) called'
                    )
                    if type(check_script["params"]) == list:
                        check_script["script"](*check_script["params"])
                    else:
                        check_script["script"](**check_script["params"])
                self.logger.debug(f'{check_script["script"].__name__}: passed\n')
            except (
                MissingDependencyError,
                GitConflictError,
                PropagatedIDChange,
                DuplicatesError,
                OriginError,
                FieldError,
                review_dataset.StatusTransitionError,
                ManuscriptRecordSourceTagError,
                UnstagedGitChangesError,
                review_dataset.StatusFieldValueError,
            ) as e:
                pass
                failure_items.append(f"{type(e).__name__}: {e}")

        if len(failure_items) > 0:
            return {"status": FAIL, "msg": "  " + "\n  ".join(failure_items)}
        else:
            return {"status": PASS, "msg": "Everything ok."}

    def report(self, *, msg_file: Path) -> dict:
        """Append commit-message report if not already available
        Entrypoint for pre-commit hooks)
        """

        update = False
        with open(msg_file, encoding="utf8") as f:
            contents = f.read()
            if "Command" not in contents:
                update = True
            if "Properties" in contents:
                update = False
        with open(msg_file, "w", encoding="utf8") as f:
            f.write(contents)
            # Don't append if it's already there
            if update:
                report = self.__get_commit_report(script_name="MANUAL", saved_args=None)
                f.write(report)

        self.REVIEW_DATASET.check_corrections_of_curated_records()

        return {"msg": "TODO", "status": 0}

    def sharing(self) -> dict:
        """Check whether sharing requirements are met
        Entrypoint for pre-commit hooks)
        """

        from colrev_core.status import Status

        STATUS = Status(REVIEW_MANAGER=self)
        stat = STATUS.get_status_freq()
        collaboration_instructions = STATUS.get_collaboration_instructions(stat=stat)
        status_code = all(
            ["SUCCESS" == x["level"] for x in collaboration_instructions["items"]]
        )
        msgs = "\n ".join(
            [
                x["level"] + x["title"] + x.get("msg", "")
                for x in collaboration_instructions["items"]
            ]
        )
        return {"msg": msgs, "status": status_code}

    def format_references(self) -> dict:
        """Format the references
        Entrypoint for pre-commit hooks)
        """

        PASS, FAIL = 0, 1
        if not self.paths["MAIN_REFERENCES"].is_file():
            return {"status": PASS, "msg": "Everything ok."}

        try:
            changed = self.REVIEW_DATASET.format_main_references()
            self.update_status_yaml()

            self.settings = self.load_settings()
            self.save_settings()

        except (UnstagedGitChangesError, review_dataset.StatusFieldValueError) as e:
            pass
            return {"status": FAIL, "msg": f"{type(e).__name__}: {e}"}

        if changed:
            return {"status": FAIL, "msg": "references formatted"}
        else:
            return {"status": PASS, "msg": "Everything ok."}

    def notify(self, *, process: Process, state_transition=True) -> None:
        """Notify the REVIEW_MANAGER about the next process"""

        if state_transition:
            process.check_precondition()
        self.notified_next_process = process.type
        self.REVIEW_DATASET.reset_log_if_no_changes()

    def __get_commit_report(
        self, *, script_name: str = None, saved_args: dict = None
    ) -> str:
        from colrev_core.status import Status

        report = "\n\nReport\n\n"

        if script_name is not None:
            if "MANUAL" == script_name:
                report = report + "Commit created manually or by external script\n\n"
            elif " " in script_name:
                script_name = (
                    script_name.replace("colrev_core", "colrev")
                    .replace("colrev cli", "colrev")
                    .replace("prescreen_cli", "prescreen")
                )
                script_name = (
                    script_name.split(" ")[0]
                    + " "
                    + script_name.split(" ")[1].replace("_", "-")
                )

                report = report + f"Command\n   {script_name}"
        if saved_args is None:
            report = report + "\n"
        else:
            report = report + " \\ \n"
            for k, v in saved_args.items():
                if (
                    isinstance(v, str)
                    or isinstance(v, bool)
                    or isinstance(v, int)
                    or isinstance(v, float)
                ):
                    if v == "":
                        report = report + f"     --{k} \\\n"
                    else:
                        report = report + f"     --{k}={v} \\\n"
            # Replace the last backslash (for argument chaining across linebreaks)
            report = report.rstrip(" \\\n") + "\n"
            try:
                last_commit_sha = self.REVIEW_DATASET.get_last_commit_sha()
                report = report + f"   On commit {last_commit_sha}\n"
            except ValueError:
                pass

        # url = g.execut['git', 'config', '--get remote.origin.url']

        # append status
        STATUS = Status(REVIEW_MANAGER=self)
        f = io.StringIO()
        with redirect_stdout(f):
            stat = STATUS.get_status_freq()
            STATUS.print_review_status(status_info=stat)

        # Remove colors for commit message
        status_page = (
            f.getvalue()
            .replace("\033[91m", "")
            .replace("\033[92m", "")
            .replace("\033[93m", "")
            .replace("\033[94m", "")
            .replace("\033[0m", "")
        )
        status_page = status_page.replace("Status\n\n", "Status\n")
        report = report + status_page

        tree_hash = self.REVIEW_DATASET.get_tree_hash()
        if self.paths["MAIN_REFERENCES"].is_file():
            tree_info = f"Properties for tree {tree_hash}\n"  # type: ignore
            report = report + "\n\n" + tree_info
            report = report + "   - Traceability of records ".ljust(38, " ") + "YES\n"
            report = (
                report + "   - Consistency (based on hooks) ".ljust(38, " ") + "YES\n"
            )
            completeness_condition = STATUS.get_completeness_condition()
            if completeness_condition:
                report = (
                    report + "   - Completeness of iteration ".ljust(38, " ") + "YES\n"
                )
            else:
                report = (
                    report + "   - Completeness of iteration ".ljust(38, " ") + "NO\n"
                )
            report = (
                report
                + "   To check tree_hash use".ljust(38, " ")
                + "git log --pretty=raw -1\n"
            )
            report = (
                report
                + "   To validate use".ljust(38, " ")
                + "colrev validate --properties\n"
                + "".ljust(38, " ")
                + "--commit INSERT_COMMIT_HASH"
            )
        report = report + "\n"

        report = report + "\nSoftware"
        rt_version = version("colrev_core")
        report = report + "\n   - colrev_core:".ljust(33, " ") + "version " + rt_version
        version("colrev_hooks")
        report = (
            report
            + "\n   - colrev hooks:".ljust(33, " ")
            + "version "
            + version("colrev_hooks")
        )
        sys_v = sys.version
        report = (
            report
            + "\n   - Python:".ljust(33, " ")
            + "version "
            + sys_v[: sys_v.find(" ")]
        )

        stream = os.popen("git --version")
        git_v = stream.read()
        report = (
            report
            + "\n   - Git:".ljust(33, " ")
            + git_v.replace("git ", "").replace("\n", "")
        )
        stream = os.popen("docker --version")
        docker_v = stream.read()
        report = (
            report
            + "\n   - Docker:".ljust(33, " ")
            + docker_v.replace("Docker ", "").replace("\n", "")
        )
        if script_name is not None:
            ext_script = script_name.split(" ")[0]
            if ext_script != "colrev_core":
                try:
                    script_version = version(ext_script)
                    report = (
                        report
                        + f"\n   - {ext_script}:".ljust(33, " ")
                        + "version "
                        + script_version
                    )
                except importlib.metadata.PackageNotFoundError:
                    pass

        if "dirty" in report:
            report = (
                report + "\n    * created with a modified version (not reproducible)"
            )
        report = report + "\n"

        return report

    def __get_version_flag(self) -> str:
        flag = ""
        if "dirty" in version("colrev_core"):
            flag = "*"
        return flag

    def update_status_yaml(self) -> None:
        from colrev_core.status import Status

        STATUS = Status(REVIEW_MANAGER=self)

        status_freq = STATUS.get_status_freq()
        with open(self.paths["STATUS"], "w", encoding="utf8") as f:
            yaml.dump(status_freq, f, allow_unicode=True)

        self.REVIEW_DATASET.add_changes(path=self.paths["STATUS_RELATIVE"])

        return

    def get_status(self) -> dict:
        status_dict = {}
        with open(self.paths["STATUS"], encoding="utf8") as stream:
            try:
                status_dict = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)
                pass
        return status_dict

    def reset_log(self) -> None:

        self.report_logger.handlers[0].stream.close()  # type: ignore
        self.report_logger.removeHandler(self.report_logger.handlers[0])

        with open("report.log", "r+", encoding="utf8") as f:
            f.truncate(0)

        file_handler = logging.FileHandler("report.log")
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(formatter)
        self.report_logger.addHandler(file_handler)

        return

    def reorder_log(self, *, IDs: list, criterion=None) -> None:
        """Reorder the report.log according to an ID list (after multiprocessing)"""

        # https://docs.python.org/3/howto/logging-cookbook.html
        # #logging-to-a-single-file-from-multiple-processes

        self.report_logger.handlers[0].stream.close()  # type: ignore
        self.report_logger.removeHandler(self.report_logger.handlers[0])

        firsts = []
        ordered_items = ""
        consumed_items = []
        with open("report.log", encoding="utf8") as r:
            items = []  # type: ignore
            item = ""
            for line in r.readlines():
                if any(
                    x in line
                    for x in [
                        "[INFO] Prepare",
                        "[INFO] Completed ",
                        "[INFO] Batch size",
                        "[INFO] Summary: Prepared",
                        "[INFO] Further instructions ",
                        "[INFO] To reset the metdatata",
                        "[INFO] Summary: ",
                        "[INFO] Continuing batch ",
                        "[INFO] Load references.bib",
                        "[INFO] Calculate statistics",
                        "[INFO] ReviewManager: run ",
                        "[INFO] Retrieve PDFs",
                        "[INFO] Statistics:",
                        "[INFO] Set ",
                    ]
                ):
                    firsts.append(line)
                    continue
                if re.search(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} ", line):
                    # prep: only list "Dropped xy field" once
                    if "[INFO] Dropped " in line:
                        if any(
                            item[item.find("[INFO] Dropped ") :] in x for x in items
                        ):
                            continue
                    if item != "":
                        item = item.replace("\n\n", "\n").replace("\n\n", "\n")
                        items.append(item)
                        item = ""
                    item = line
                else:
                    item = item + line

            items.append(item.replace("\n\n", "\n").replace("\n\n", "\n"))

        if criterion is None:
            for ID in IDs:
                for item in items:
                    if f"({ID})" in item:
                        formatted_item = item
                        if "] prepare(" in formatted_item:
                            formatted_item = f"\n\n{formatted_item}"
                        ordered_items = ordered_items + formatted_item
                        consumed_items.append(item)

            for x in consumed_items:
                if x in items:
                    items.remove(x)

        if criterion == "descending_thresholds":
            item_details = []
            while items:
                item = items.pop()
                confidence_value = re.search(r"\(confidence: (\d.\d{0,3})\)", item)
                if confidence_value:
                    item_details.append([confidence_value.group(1), item])
                    consumed_items.append(item)
                else:
                    firsts.append(item)

            item_details.sort(key=lambda x: x[0])
            ordered_items = "".join([x[1] for x in item_details])

        if len(ordered_items) > 0 or len(items) > 0:
            formatted_report = (
                "".join(firsts)
                + "\nDetailed report\n"
                + ordered_items.lstrip("\n")
                + "\n\n"
                + "".join(items)
            )
        else:
            formatted_report = "".join(firsts)

        with open("report.log", "w", encoding="utf8") as f:
            f.write(formatted_report)

        file_handler = logging.FileHandler("report.log")
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(formatter)
        self.report_logger.addHandler(file_handler)

        return

    def create_commit(
        self,
        *,
        msg: str,
        manual_author: bool = False,
        saved_args: dict = None,
        realtime_override: bool = False,
    ) -> bool:
        """Create a commit (including a commit report)"""

        # if "realtime" == self.settings.project.review_type and not realtime_override:
        #     return False

        if self.REVIEW_DATASET.has_changes():

            self.update_status_yaml()
            self.REVIEW_DATASET.add_changes(path=self.paths["STATUS_RELATIVE"])

            hook_skipping = False
            if not self.DEBUG_MODE:
                hook_skipping = True

            processing_report = ""
            if self.paths["REPORT"].is_file():

                # Reformat
                prefixes = [
                    "[('change', 'author',",
                    "[('change', 'title',",
                    "[('change', 'journal',",
                    "[('change', 'booktitle',",
                ]
                temp = tempfile.NamedTemporaryFile(mode="r+b", delete=False)
                with open(self.paths["REPORT"], "r+b") as f:
                    shutil.copyfileobj(f, temp)
                # self.paths["REPORT"].rename(temp.name)
                with open(temp.name, encoding="utf8") as reader, open(
                    self.paths["REPORT"], "w"
                ) as writer:
                    line = reader.readline()
                    while line:
                        if (
                            any(prefix in line for prefix in prefixes)
                            and "', '" in line[30:]
                        ):
                            split_pos = line.rfind("', '") + 2
                            indent = line.find("', (") + 3
                            writer.write(line[:split_pos] + "\n")
                            writer.write(" " * indent + line[split_pos:])
                        else:
                            writer.write(line)

                        line = reader.readline()

                with open("report.log", encoding="utf8") as f:
                    line = f.readline()
                    debug_part = False
                    while line:
                        # For more efficient debugging (loading of dict with Enum)
                        if "colrev_status" in line and "<RecordState." in line:
                            line = line.replace("<RecordState", "RecordState")
                            line = line[: line.rfind(":")] + line[line.rfind(">") + 1 :]
                        if "[DEBUG]" in line or debug_part:
                            debug_part = True
                            if any(
                                x in line
                                for x in ["[INFO]", "[ERROR]", "[WARNING]", "[CRITICAL"]
                            ):
                                debug_part = False
                        if not debug_part:
                            processing_report = processing_report + line
                        line = f.readline()

                processing_report = "\nProcessing report\n" + "".join(processing_report)

            caller = sys._getframe(1)
            from inspect import stack

            script = (
                str(caller.f_globals["__name__"]).replace("-", "_").replace(".", " ")
                + " "
                + str(stack()[1].function)
            )
            if "Update pre-commit-config" in msg:
                script = "pre-commit autoupdate"
            # TODO: test and update the following
            if "__apply_correction" in script:
                script = "apply_corrections"

            if manual_author:
                git_author = git.Actor(self.COMMITTER, self.EMAIL)
            else:
                git_author = git.Actor(f"script:{script}", "")
            # TODO: test and update the following
            if "apply_correction" in script:
                cmsg = msg
            else:
                cmsg = (
                    msg
                    + self.__get_version_flag()
                    + self.__get_commit_report(
                        script_name=f"{script}", saved_args=saved_args
                    )
                    + processing_report
                )
            self.REVIEW_DATASET.create_commit(
                msg=cmsg,
                author=git_author,
                committer=git.Actor(self.COMMITTER, self.EMAIL),
                hook_skipping=hook_skipping,
            )

            self.logger.info("Created commit")
            self.reset_log()
            if self.REVIEW_DATASET.has_changes():
                raise DirtyRepoAfterProcessingError
            return True
        else:
            return False


class MissingDependencyError(Exception):
    def __init__(self, dep):
        self.message = f"{dep}"
        super().__init__(self.message)


class SoftwareUpgradeError(Exception):
    def __init__(self, old, new):
        self.message = (
            f"Detected upgrade from {old} to {new}. To upgrade use\n     "
            "colrev config --upgrade"
        )
        super().__init__(self.message)


class GitConflictError(Exception):
    def __init__(self, path):
        self.message = f"please resolve git conflict in {path}"
        super().__init__(self.message)


class DirtyRepoAfterProcessingError(Exception):
    pass


class ConsistencyError(Exception):
    pass


class RepoSetupError(Exception):
    def __init__(self, msg):
        self.message = f" {msg}"
        super().__init__(self.message)


class SearchDetailsMissingError(Exception):
    def __init__(
        self,
        search_results_path,
    ):
        self.message = (
            "Search results path "
            + f"({search_results_path.name}) "
            + "is not in sources.yaml"
        )
        super().__init__(self.message)


if __name__ == "__main__":
    pass
