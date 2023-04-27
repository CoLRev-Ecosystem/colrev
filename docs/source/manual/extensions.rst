
Extensions
==================================

CoLRev comes with batteries included, i.e., a reference implementation for all steps of the process.
At the same time you can easily include other extensions or custom scripts (batteries are swappable).
Everything is specified in the settings.json (simply add the extension/script name as the endpoint in the ``settings.json`` of the project):


.. code-block:: diff

   ...
    "screen": {
        "criteria": [],
        "screen_package_endpoints": [
            {
   -             "endpoint": "colrev.colrev_cli_screen"
   +             "endpoint": "custom_screen_script"
            }
        ]
    },
    ...

The interfaces for the extension endpoints are documented in the `extension interfaces <../foundations/extensions.html>`_ section.

Registered extensions are public Python packages that can be installed via PyPI.
They contain an ``.colrev_endpoints.json`` file in the top-level directory (`colrev <https://github.com/CoLRev-Environment/colrev/blob/main/.colrev_endpoints.json>`_ provides an example).
To register a new extension, create a pull request briefly describing the extension and adding it to the `packages.json <https://github.com/CoLRev-Environment/colrev/blob/main/colrev/template/packages.json>`_.
When the review is passed, the details will be added to the `package_endpoints.json <https://github.com/CoLRev-Environment/colrev/blob/main/colrev/template/package_endpoints.json>`_, which also makes them available in the documentation.
The development status is automatically added to the `package_status.json <https://github.com/CoLRev-Environment/colrev/blob/main/colrev/template/package_status.json>`_ and can be updated manually once the review is completed.

**Recommendations**:

- Get paths from ``review_manager``
- Use the ``logger`` and ``colrev_report_logger`` to help users examine and validate the process, including links to the docs where instructions for tracing and fixing errors are available.
- `Add <https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics>`_ the ```colrev-extension``` `topic tag on GitHub <https://github.com/topics/colrev-extension>`_ to allow others to find and use your work.

..
    Mention scripts and non-public python projects
    Check: when packages don't meet the interface specifications, they will automatically fail/be excluded


.. toctree::
   :maxdepth: 3
   :caption: Extension development resources

   extensions/development
   extensions/python
   extensions/r
   extensions/custom_extensions
