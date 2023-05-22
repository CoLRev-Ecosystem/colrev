colrev.dataset.Dataset
======================

.. currentmodule:: colrev.dataset

.. autoclass:: Dataset
   :members:
   :show-inheritance:
   :inherited-members:
   :special-members: __call__, __add__, __mul__



   .. rubric:: Methods

   .. autosummary::
      :nosignatures:

      ~Dataset.add_changes
      ~Dataset.add_record_changes
      ~Dataset.add_setting_changes
      ~Dataset.behind_remote
      ~Dataset.create_commit
      ~Dataset.file_in_history
      ~Dataset.format_records_file
      ~Dataset.generate_next_unique_id
      ~Dataset.get_changed_records
      ~Dataset.get_commit_message
      ~Dataset.get_committed_origin_state_dict
      ~Dataset.get_last_commit_sha
      ~Dataset.get_next_id
      ~Dataset.get_nr_in_bib
      ~Dataset.get_origin_state_dict
      ~Dataset.get_remote_url
      ~Dataset.get_repo
      ~Dataset.get_tree_hash
      ~Dataset.get_untracked_files
      ~Dataset.has_changes
      ~Dataset.has_untracked_search_records
      ~Dataset.load_records_dict
      ~Dataset.load_records_from_history
      ~Dataset.parse_bibtex_str
      ~Dataset.parse_records_dict
      ~Dataset.propagated_id
      ~Dataset.pull_if_repo_clean
      ~Dataset.read_next_record
      ~Dataset.records_changed
      ~Dataset.remote_ahead
      ~Dataset.remove_file_from_git
      ~Dataset.reprocess_id
      ~Dataset.reset_log_if_no_changes
      ~Dataset.save_records_dict
      ~Dataset.save_records_dict_to_file
      ~Dataset.set_ids
      ~Dataset.update_gitignore





   .. rubric:: Attributes

   .. autosummary::

      ~Dataset.DEFAULT_GIT_IGNORE_ITEMS
      ~Dataset.DEPRECATED_GIT_IGNORE_ITEMS
      ~Dataset.GIT_IGNORE_FILE_RELATIVE
      ~Dataset.RECORDS_FILE_RELATIVE
      ~Dataset.records_file
