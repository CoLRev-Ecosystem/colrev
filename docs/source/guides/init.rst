
Init
==================================

:program:`colrev init` initializes a new CoLRev project. It should be called in an empty directory.

.. code:: bash

	colrev init [options]

.. program:: colrev init

.. option:: --name

    Name of the project

.. option:: --curated_metadata

    Use a template for curated metadata repositories.

.. option:: --url

    Url for the curated metadata repository.


Once the repository is set up, you can share it with your team (see `instructions <overview.html#collaborate-in-a-team>`_).

Instead of initializing a new repository, you can also pull an existing one:

.. code:: bash

	git pull https://github.com/u_name/repo_name.git
